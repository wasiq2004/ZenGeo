"""Audit intake: turn a questionnaire into a queued audit run."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.audit import Audit, AuditStatus
from app.db.models.business import Business
from app.db.models.llm_key import LLMApiKey
from app.schemas.audit import AuditCreate
from app.schemas.business import BusinessCreate

log = get_logger("audits")


class AuditIntakeError(Exception):
    """The audit cannot be created as requested."""


async def _resolve_business(
    db: AsyncSession, *, user_id: uuid.UUID, payload: AuditCreate
) -> Business:
    """Find the referenced business, or create/update one from the wizard."""
    if payload.business_id is not None:
        business = await db.scalar(
            select(Business).where(
                Business.id == payload.business_id, Business.user_id == user_id
            )
        )
        if business is None:
            raise AuditIntakeError("Business not found")
        if payload.business is not None:
            # The wizard let them edit the prefilled details - keep them.
            for field, value in payload.business.model_dump().items():
                setattr(business, field, value)
        return business

    assert payload.business is not None  # guaranteed by AuditCreate validation
    details: BusinessCreate = payload.business
    business = Business(user_id=user_id, **details.model_dump())
    db.add(business)
    await db.flush()
    return business


async def count_active_providers(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Providers that will actually be tested, in registry order."""
    records = await db.scalars(
        select(LLMApiKey).where(LLMApiKey.user_id == user_id, LLMApiKey.is_active.is_(True))
    )
    providers: list[str] = []
    for record in records:
        if record.provider.value not in providers:
            providers.append(record.provider.value)
    return providers


async def create_audit(
    db: AsyncSession, *, user_id: uuid.UUID, payload: AuditCreate
) -> tuple[Audit, list[str], int]:
    """Create a pending audit. Returns (audit, providers, planned LLM calls)."""
    business = await _resolve_business(db, user_id=user_id, payload=payload)

    providers = await count_active_providers(db, user_id)
    prompts = payload.questionnaire.target_prompts
    # One call per prompt per provider. Shown to the user before anything runs
    # so the spend on their own key is never a surprise - it is not a cap.
    planned_calls = len(prompts) * len(providers)

    audit = Audit(
        user_id=user_id,
        business_id=business.id,
        status=AuditStatus.pending,
        questionnaire_answers=payload.questionnaire.model_dump(mode="json"),
        progress=0,
    )
    db.add(audit)
    await db.flush()

    log.info(
        "audit_created",
        audit_id=str(audit.id),
        user_id=str(user_id),
        prompts=len(prompts),
        providers=len(providers),
        planned_llm_calls=planned_calls,
    )
    return audit, providers, planned_calls


def enqueue_audit(audit_id: uuid.UUID) -> None:
    """Hand the audit to the worker.

    Imported lazily so the API process never pulls in worker-only dependencies
    at import time, and so a broker outage surfaces here rather than at boot.
    """
    from app.worker.tasks import run_audit

    run_audit.delay(str(audit_id))
    log.info("audit_enqueued", audit_id=str(audit_id))
