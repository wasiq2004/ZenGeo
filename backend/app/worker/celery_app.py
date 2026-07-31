"""Celery application for long-running audit work.

Audits fetch many external pages and may make a large number of LLM calls, so
they never run inside a request. The API enqueues a task and the SPA polls the
audit's status.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging

from app.core.config import settings
from app.core.logging import configure_logging

celery_app = Celery(
    "geo_audit",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # An audit's cost lands on the user's own API key, so a silent retry could
    # spend their money twice. Retries are decided explicitly inside the task.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    result_expires=86_400,
    broker_connection_retry_on_startup=True,
    # Hard ceiling so a hung external request cannot occupy a worker forever.
    task_time_limit=3_600,
    task_soft_time_limit=3_300,
)


@setup_logging.connect
def _configure_worker_logging(**_kwargs: object) -> None:
    """Use the app's structured logger inside the worker too."""
    configure_logging(settings.log_level, settings.log_format)
