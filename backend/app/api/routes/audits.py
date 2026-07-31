"""Audit endpoints: start a run, poll its progress, read the results."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, Pagination, VerifiedUser
from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import RateLimit
from app.db.models.audit import Audit, AuditStatus
from app.db.models.business import Business
from app.schemas.audit import (
    AuditCreate,
    AuditDetail,
    AuditEventPublic,
    AuditStartResponse,
    AuditSummary,
)
from app.schemas.common import Message, Page
from app.services import audits as audit_service

router = APIRouter(prefix="/audits", tags=["audits"])
log = get_logger("audits.routes")

start_limit = RateLimit(settings.rate_limit_audit_start, scope="audit-start")


def _summary(audit: Audit, business: Business | None) -> AuditSummary:
    return AuditSummary(
        id=audit.id,
        business_id=audit.business_id,
        status=audit.status,
        geo_score=float(audit.geo_score) if audit.geo_score is not None else None,
        score_band=audit.score_band,
        progress=float(audit.progress or 0),
        created_at=audit.created_at,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
        business_name=business.name if business else "",
        website_url=business.website_url if business else "",
        has_report=bool(audit.pdf_report_path),
    )


async def _owned_audit(db: DbSession, user_id: uuid.UUID, audit_id: uuid.UUID) -> Audit:
    audit = await db.scalar(
        select(Audit)
        .where(Audit.id == audit_id, Audit.user_id == user_id)
        .options(selectinload(Audit.business), selectinload(Audit.events))
    )
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


@router.post(
    "",
    response_model=AuditStartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(start_limit)],
    summary="Start an audit",
)
async def start_audit(
    payload: AuditCreate, user: VerifiedUser, db: DbSession
) -> AuditStartResponse:
    """Creates the audit and queues it. Returns immediately - the scan and any
    Share of Voice calls run in the background worker."""
    try:
        audit, providers, planned_calls = await audit_service.create_audit(
            db, user_id=user.id, payload=payload
        )
    except audit_service.AuditIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(audit, ["business"])

    try:
        audit_service.enqueue_audit(audit.id)
    except Exception as exc:
        # The audit row survives so the user can retry without re-entering the
        # questionnaire; the status makes the failure explicit.
        audit.status = AuditStatus.failed
        audit.error_message = "Could not queue the audit. The job runner may be down."
        await db.commit()
        log.error("audit_enqueue_failed", audit_id=str(audit.id), error=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not queue the audit right now. Please try again shortly.",
        ) from exc

    if providers:
        message = (
            f"Audit queued. Share of Voice will make {planned_calls} call(s) "
            f"across {len(providers)} provider(s) using your own API keys."
        )
    else:
        message = (
            "Audit queued. No AI provider key is connected, so Share of Voice will be "
            "skipped and its weight redistributed across the other six pillars."
        )

    return AuditStartResponse(
        audit=_summary(audit, audit.business),
        planned_llm_calls=planned_calls,
        providers=providers,
        message=message,
    )


@router.get("", response_model=Page[AuditSummary], summary="Your audit history")
async def list_audits(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    business_id: uuid.UUID | None = Query(default=None),
    audit_status: AuditStatus | None = Query(default=None, alias="status"),
) -> Page[AuditSummary]:
    filters = [Audit.user_id == user.id]
    if business_id:
        filters.append(Audit.business_id == business_id)
    if audit_status:
        filters.append(Audit.status == audit_status)

    total = await db.scalar(select(func.count()).select_from(Audit).where(*filters)) or 0
    records = await db.scalars(
        select(Audit)
        .where(*filters)
        .options(selectinload(Audit.business))
        .order_by(Audit.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    return Page[AuditSummary](
        items=[_summary(audit, audit.business) for audit in records],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{audit_id}", response_model=AuditDetail, summary="Full audit result")
async def get_audit(audit_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AuditDetail:
    audit = await _owned_audit(db, user.id, audit_id)
    summary = _summary(audit, audit.business)
    return AuditDetail(
        **summary.model_dump(),
        questionnaire_answers=audit.questionnaire_answers or {},
        pillar_scores=audit.pillar_scores,
        share_of_voice_results=audit.share_of_voice_results,
        recommendations=audit.recommendations,
        raw_findings=audit.raw_findings,
        error_message=audit.error_message,
        events=[AuditEventPublic.model_validate(event) for event in audit.events],
    )


@router.get(
    "/{audit_id}/status",
    response_model=AuditSummary,
    summary="Lightweight progress poll",
)
async def get_audit_status(
    audit_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> AuditSummary:
    """Cheap endpoint for the progress screen - no events, no result blobs."""
    audit = await db.scalar(
        select(Audit)
        .where(Audit.id == audit_id, Audit.user_id == user.id)
        .options(selectinload(Audit.business))
    )
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return _summary(audit, audit.business)


@router.get(
    "/{audit_id}/events",
    response_model=list[AuditEventPublic],
    summary="Stage-by-stage progress log",
)
async def get_audit_events(
    audit_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[AuditEventPublic]:
    audit = await _owned_audit(db, user.id, audit_id)
    return [AuditEventPublic.model_validate(event) for event in audit.events]


@router.delete("/{audit_id}", response_model=Message, summary="Delete an audit")
async def delete_audit(audit_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    audit = await _owned_audit(db, user.id, audit_id)
    if audit.status is AuditStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This audit is still running. Wait for it to finish before deleting it.",
        )

    from app.services.report import delete_report_file

    delete_report_file(audit)
    await db.delete(audit)
    await db.commit()
    return Message(detail="Audit deleted.")
