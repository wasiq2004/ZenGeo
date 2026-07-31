"""User dashboard KPIs.

Aggregated in SQL rather than in Python so the payload stays small and the
dashboard stays fast as a user's audit history grows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.db.models.audit import Audit, AuditStatus
from app.db.models.business import Business
from app.db.models.llm_key import LLMApiKey
from app.schemas.audit import AuditSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TREND_LIMIT = 20


@router.get("/stats", summary="Your KPI summary")
async def dashboard_stats(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    totals = (
        await db.execute(
            select(
                func.count(Audit.id),
                func.count(case((Audit.status == AuditStatus.completed, 1))),
                func.count(
                    case((Audit.status.in_([AuditStatus.pending, AuditStatus.running]), 1))
                ),
                func.avg(case((Audit.status == AuditStatus.completed, Audit.geo_score))),
                func.max(case((Audit.status == AuditStatus.completed, Audit.geo_score))),
            ).where(Audit.user_id == user.id)
        )
    ).one()

    total_audits, completed, running, average, best = totals

    # Score trend: completed audits oldest-first so the chart reads left to right.
    trend_rows = list(
        await db.execute(
            select(Audit.geo_score, Audit.completed_at, Business.name)
            .join(Business, Business.id == Audit.business_id)
            .where(
                Audit.user_id == user.id,
                Audit.status == AuditStatus.completed,
                Audit.geo_score.is_not(None),
            )
            .order_by(Audit.completed_at.desc())
            .limit(TREND_LIMIT)
        )
    )
    trend = [
        {
            "date": (completed_at or datetime.now(UTC)).date().isoformat(),
            "score": float(score),
            "business": name,
        }
        for score, completed_at, name in reversed(trend_rows)
    ]

    latest_score = trend[-1]["score"] if trend else None
    previous_score = trend[-2]["score"] if len(trend) > 1 else None
    delta = (
        round(latest_score - previous_score, 1)
        if latest_score is not None and previous_score is not None
        else None
    )

    # Average per pillar across completed audits, so the dashboard can show
    # which dimension is dragging the score down overall.
    pillar_rows = await db.scalars(
        select(Audit.pillar_scores).where(
            Audit.user_id == user.id,
            Audit.status == AuditStatus.completed,
            Audit.pillar_scores.is_not(None),
        )
    )
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for pillar_scores in pillar_rows:
        for key, data in (pillar_scores or {}).items():
            if isinstance(data, dict) and not data.get("skipped"):
                sums[key] = sums.get(key, 0.0) + float(data.get("score") or 0)
                counts[key] = counts.get(key, 0) + 1
    pillar_averages = {key: round(sums[key] / counts[key], 1) for key in sums if counts[key]}

    recent = await db.scalars(
        select(Audit)
        .where(Audit.user_id == user.id)
        .options(selectinload(Audit.business))
        .order_by(Audit.created_at.desc())
        .limit(5)
    )

    providers = await db.scalars(
        select(LLMApiKey.provider)
        .where(LLMApiKey.user_id == user.id, LLMApiKey.is_active.is_(True))
        .distinct()
    )

    return {
        "total_audits": total_audits or 0,
        "completed_audits": completed or 0,
        "running_audits": running or 0,
        "average_score": round(float(average), 1) if average is not None else None,
        "best_score": round(float(best), 1) if best is not None else None,
        "latest_score": latest_score,
        "score_delta": delta,
        "connected_providers": [provider.value for provider in providers],
        "score_trend": trend,
        "pillar_averages": pillar_averages,
        "recent_audits": [
            AuditSummary(
                id=audit.id,
                business_id=audit.business_id,
                status=audit.status,
                geo_score=float(audit.geo_score) if audit.geo_score is not None else None,
                score_band=audit.score_band,
                progress=float(audit.progress or 0),
                created_at=audit.created_at,
                started_at=audit.started_at,
                completed_at=audit.completed_at,
                business_name=audit.business.name if audit.business else "",
                website_url=audit.business.website_url if audit.business else "",
                has_report=bool(audit.pdf_report_path),
            ).model_dump(mode="json")
            for audit in recent
        ],
    }


@router.get("/activity", summary="Audit counts per day")
async def audit_activity(user: CurrentUser, db: DbSession, days: int = 30) -> list[dict[str, Any]]:
    """Daily audit counts for the sparkline, zero-filled so gaps show as gaps."""
    days = max(7, min(days, 365))
    since = datetime.now(UTC) - timedelta(days=days)

    rows = await db.execute(
        select(func.date(Audit.created_at), func.count(Audit.id))
        .where(Audit.user_id == user.id, Audit.created_at >= since)
        .group_by(func.date(Audit.created_at))
    )
    counts = {row[0].isoformat(): row[1] for row in rows}

    start = (datetime.now(UTC) - timedelta(days=days - 1)).date()
    return [
        {
            "date": (start + timedelta(days=offset)).isoformat(),
            "count": counts.get((start + timedelta(days=offset)).isoformat(), 0),
        }
        for offset in range(days)
    ]
