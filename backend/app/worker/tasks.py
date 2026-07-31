"""Celery tasks.

Celery workers are synchronous; the audit engine is async. Each task opens its
own event loop with `asyncio.run`.

That makes engine lifecycle load-bearing: asyncpg connections belong to the
loop that created them, so a pooled connection from a previous task is unusable
in the next one. `run_in_loop` guarantees the engine is disposed before the
loop closes, so every task starts with a clean pool.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any

from app.core.logging import get_logger
from app.worker.celery_app import celery_app

log = get_logger("worker")


def run_in_loop[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine in a fresh loop, disposing the DB engine afterwards."""

    async def _wrapped() -> T:
        from app.db.session import dispose_engine

        try:
            return await coro
        finally:
            # Must happen inside the loop that owns the connections.
            await dispose_engine()

    return asyncio.run(_wrapped())


@celery_app.task(name="geo.ping")
def ping() -> str:
    """Smoke test that the worker can accept and complete a task."""
    return "pong"


@celery_app.task(
    name="geo.run_audit",
    bind=True,
    # Not autoretried: an audit spends the user's own API credit, so a silent
    # retry could bill them twice for the same run. Failures surface on the
    # audit record instead, and the user decides whether to run it again.
    max_retries=0,
    acks_late=True,
)
def run_audit(self, audit_id: str) -> str:  # type: ignore[no-untyped-def]
    from app.audit.runner import execute_audit

    log.info("worker_audit_start", audit_id=audit_id, task_id=self.request.id)
    try:
        run_in_loop(execute_audit(uuid.UUID(audit_id)))
    except Exception:
        log.exception("worker_audit_crashed", audit_id=audit_id)
        # Mark the audit failed so the UI stops showing a spinner forever.
        run_in_loop(_mark_failed(uuid.UUID(audit_id)))
        raise
    return audit_id


async def _mark_failed(audit_id: uuid.UUID) -> None:
    from datetime import UTC, datetime

    from app.db.models.audit import Audit, AuditStatus
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        audit = await db.get(Audit, audit_id)
        if audit is not None and audit.status is not AuditStatus.completed:
            audit.status = AuditStatus.failed
            audit.error_message = (
                "The audit worker stopped unexpectedly. Please try running the audit again."
            )
            audit.completed_at = datetime.now(UTC)
            await db.commit()


@celery_app.task(
    name="geo.send_email",
    bind=True,
    # Unlike an audit, re-sending is cheap and idempotent from the user's point
    # of view, so a transient provider outage is worth retrying through.
    # Backoff is capped and jittered so a Resend incident does not turn our
    # whole queue into a synchronised retry storm against them.
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def send_email_task(self, kind: str, to: str, context: dict[str, object]) -> str:  # type: ignore[no-untyped-def]
    """Render and send one transactional message.

    The payload is the render context, not a rendered body - it keeps the queue
    entry small, and a template fix reaches anything still waiting in it.
    """
    from app.services.email import send_now

    try:
        message_id = run_in_loop(send_now(kind, to=to, context=context))
    except Exception as exc:
        log.warning(
            "email_task_retrying",
            kind=kind,
            to=to,
            attempt=self.request.retries + 1,
            max_retries=self.max_retries,
            error=str(exc),
        )
        raise

    log.info("email_task_done", kind=kind, to=to, provider_id=message_id or None)
    return message_id


@celery_app.task(name="geo.regenerate_report")
def regenerate_report(audit_id: str) -> str:
    """Rebuild a PDF without re-running the audit (and without re-spending)."""

    async def _run() -> None:
        from app.db.models.audit import Audit
        from app.db.session import SessionLocal
        from app.services.report import generate_report

        path = await generate_report(uuid.UUID(audit_id))
        async with SessionLocal() as db:
            audit = await db.get(Audit, uuid.UUID(audit_id))
            if audit is not None:
                audit.pdf_report_path = str(path)
                await db.commit()

    run_in_loop(_run())
    return audit_id
