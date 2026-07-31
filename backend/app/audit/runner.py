"""Audit orchestration.

Runs the pillars in order, commits progress after each so the UI's poll shows
real movement, and never lets one pillar's failure lose the others' work.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.audit.context import AuditContext
from app.audit.fetcher import SafeFetcher
from app.audit.pillars import AUTOMATED_PILLARS, ShareOfVoicePillar
from app.audit.pillars.base import PillarResult
from app.audit.scoring import compute_composite, prioritise_recommendations
from app.core.logging import get_logger
from app.db.models.audit import Audit, AuditEvent, AuditStatus
from app.db.models.user import User
from app.db.session import SessionLocal
from app.llm import LLMProvider
from app.services import llm_keys as key_service

log = get_logger("audit.runner")

#: Share of Voice can make many calls, so it gets the largest slice of the bar.
STAGE_WEIGHTS = {
    "fetch": 5,
    "crawlability": 10,
    "llms_txt": 8,
    "structured_data": 10,
    "extractability": 12,
    "evidence": 10,
    "entity_authority": 10,
    "share_of_voice": 25,
    "report": 10,
}


class AuditRunner:
    def __init__(self, audit_id: uuid.UUID) -> None:
        self.audit_id = audit_id
        self.progress = 0.0

    async def _record_event(self, stage: str, message: str, level: str = "info") -> None:
        """Append a progress event in its own transaction so the UI sees it now."""
        async with SessionLocal() as db:
            db.add(
                AuditEvent(
                    audit_id=self.audit_id,
                    stage=stage,
                    level=level,
                    message=message[:2000],
                )
            )
            await db.commit()

    async def _advance(self, stage: str) -> None:
        self.progress = min(99.0, self.progress + STAGE_WEIGHTS.get(stage, 5))
        async with SessionLocal() as db:
            audit = await db.get(Audit, self.audit_id)
            if audit is not None:
                audit.progress = self.progress
                await db.commit()

    async def run(self) -> None:
        started = time.perf_counter()

        async with SessionLocal() as db:
            audit = await db.scalar(
                select(Audit)
                .where(Audit.id == self.audit_id)
                .options(selectinload(Audit.business))
            )
            if audit is None:
                log.error("audit_missing", audit_id=str(self.audit_id))
                return
            if audit.status is AuditStatus.completed:
                log.info("audit_already_complete", audit_id=str(self.audit_id))
                return

            audit.status = AuditStatus.running
            audit.started_at = datetime.now(UTC)
            audit.progress = 0
            audit.error_message = None
            business = audit.business
            user_id = audit.user_id
            questionnaire: dict[str, Any] = dict(audit.questionnaire_answers or {})
            # Snapshotted while the session is open: the ORM object is detached
            # once we leave this block, and the pillars run outside it.
            business_snapshot: dict[str, Any] = {
                "name": business.name,
                "website_url": business.website_url,
                "industry": business.industry,
                "description": business.description,
                "location": business.location,
                "competitors": list(business.competitors or []),
                "key_pages": list(business.key_pages or []),
            }
            await db.commit()

        await self._record_event("start", f"Audit started for {business_snapshot['name']}.")

        try:
            results, raw_findings = await self._run_pillars(
                user_id=user_id, business=business_snapshot, questionnaire=questionnaire
            )
        except Exception as exc:
            log.exception("audit_failed", audit_id=str(self.audit_id))
            await self._fail(f"The audit could not be completed: {type(exc).__name__}")
            return

        composite = compute_composite(results)
        recommendations = prioritise_recommendations(results)

        async with SessionLocal() as db:
            audit = await db.get(Audit, self.audit_id)
            if audit is None:
                return
            audit.pillar_scores = {result.key: result.to_dict() for result in results}
            audit.geo_score = composite.score
            audit.score_band = composite.band
            audit.recommendations = recommendations
            audit.raw_findings = raw_findings

            sov = next((r for r in results if r.key == "share_of_voice"), None)
            audit.share_of_voice_results = _share_of_voice_payload(sov)

            audit.progress = 90
            await db.commit()

        await self._record_event(
            "scoring",
            f"GEO score: {composite.score:.0f}/100 ({composite.band})."
            + (
                " Share of Voice was skipped, so its weight was redistributed across the"
                " other pillars."
                if composite.redistributed
                else ""
            ),
        )

        await self._build_report()

        async with SessionLocal() as db:
            audit = await db.get(Audit, self.audit_id)
            if audit is not None:
                audit.status = AuditStatus.completed
                audit.completed_at = datetime.now(UTC)
                audit.progress = 100
                await db.commit()

        elapsed = time.perf_counter() - started
        await self._record_event(
            "done", f"Audit complete in {elapsed:.1f}s. Score {composite.score:.0f}/100."
        )
        log.info(
            "audit_completed",
            audit_id=str(self.audit_id),
            score=composite.score,
            band=composite.band,
            duration_s=round(elapsed, 2),
        )
        await self._notify(composite.score, composite.band, str(business_snapshot["name"]))

    async def _run_pillars(
        self, *, user_id: uuid.UUID, business: dict[str, Any], questionnaire: dict[str, Any]
    ) -> tuple[list[PillarResult], dict[str, Any]]:
        results: list[PillarResult] = []
        raw_findings: dict[str, Any] = {}

        providers = await self._load_providers(user_id)

        async with SafeFetcher() as fetcher:
            ctx = AuditContext(
                business_name=business["name"],
                website_url=business["website_url"],
                industry=business["industry"],
                description=business["description"],
                location=business["location"],
                competitors=business["competitors"],
                key_pages=business["key_pages"],
                questionnaire=questionnaire,
                fetcher=fetcher,
                emit=self._record_event,
            )

            await self._record_event("fetch", f"Fetching {ctx.website_url}…")
            await ctx.homepage()
            await self._advance("fetch")

            for pillar_cls in AUTOMATED_PILLARS:
                pillar = pillar_cls()
                await self._record_event(pillar.key, f"Checking {pillar.name}…")
                try:
                    result = await pillar.run(ctx)
                except Exception as exc:
                    # One broken pillar must not cost the user the other five.
                    log.exception("pillar_failed", pillar=pillar.key, audit_id=str(self.audit_id))
                    result = pillar.failed(
                        f"This check could not be completed ({type(exc).__name__})."
                    )
                    await self._record_event(
                        pillar.key, f"{pillar.name} could not be completed.", "error"
                    )

                results.append(result)
                raw_findings[result.key] = result.findings
                await self._record_event(
                    result.key, f"{pillar.name}: {result.score:.0f}/100. {result.summary}"
                )
                await self._advance(result.key)

            sov_pillar = ShareOfVoicePillar(providers)
            try:
                sov_result = await sov_pillar.run(ctx)
            except Exception as exc:
                log.exception("sov_failed", audit_id=str(self.audit_id))
                sov_result = sov_pillar.failed(
                    f"Share of Voice testing could not be completed ({type(exc).__name__})."
                )
            results.append(sov_result)
            raw_findings[sov_result.key] = sov_result.findings
            await self._record_event(
                sov_result.key,
                sov_result.skip_reason or f"{sov_pillar.name}: {sov_result.summary}",
            )
            await self._advance("share_of_voice")

            raw_findings["pages_fetched"] = {
                url: {
                    "status": snapshot.fetch.status_code,
                    "content_type": snapshot.fetch.content_type,
                    "bytes": len(snapshot.fetch.text),
                    "error": snapshot.fetch.error,
                }
                for url, snapshot in ctx.pages.items()
            }

        await self._mark_keys_used(user_id, providers)
        return results, raw_findings

    async def _load_providers(self, user_id: uuid.UUID) -> list[tuple[str, LLMProvider]]:
        """Adapters for every active key, labelled for the results table."""
        async with SessionLocal() as db:
            pairs = await key_service.active_providers_for_user(db, user_id)

        providers: list[tuple[str, LLMProvider]] = []
        for record, provider in pairs:
            label = record.provider.value
            # Two keys for one provider get distinct labels so results stay readable.
            if any(existing == label for existing, _ in providers):
                label = f"{label}:{record.label}"
            providers.append((label, provider))
        return providers

    async def _mark_keys_used(
        self, user_id: uuid.UUID, providers: list[tuple[str, LLMProvider]]
    ) -> None:
        if not providers:
            return
        async with SessionLocal() as db:
            for record in await key_service.list_keys(db, user_id):
                if record.is_active:
                    record.last_used_at = datetime.now(UTC)
            await db.commit()

    async def _build_report(self) -> None:
        from app.services.report import generate_report

        await self._record_event("report", "Building the PDF report…")
        try:
            path = await generate_report(self.audit_id)
        except Exception as exc:
            # A failed PDF must not fail the audit - the results are already saved.
            log.error("report_failed", audit_id=str(self.audit_id), error=type(exc).__name__)
            await self._record_event(
                "report", "The PDF could not be generated, but your results are saved.", "warning"
            )
            return

        async with SessionLocal() as db:
            audit = await db.get(Audit, self.audit_id)
            if audit is not None:
                audit.pdf_report_path = str(path)
                await db.commit()
        await self._record_event("report", "PDF report ready to download.")

    async def _notify(self, score: float, band: str, business_name: str) -> None:
        from app.services.email import send_audit_complete_email

        async with SessionLocal() as db:
            audit = await db.get(Audit, self.audit_id)
            if audit is None:
                return
            user = await db.get(User, audit.user_id)
            if user is None or not user.notify_audit_complete:
                return
            recipient, name = user.email, user.full_name

        await send_audit_complete_email(
            to=recipient,
            name=name,
            business=business_name,
            score=score,
            band=band,
            audit_id=str(self.audit_id),
        )

    async def _fail(self, message: str) -> None:
        async with SessionLocal() as db:
            audit = await db.get(Audit, self.audit_id)
            if audit is not None:
                audit.status = AuditStatus.failed
                audit.error_message = message
                audit.completed_at = datetime.now(UTC)
                await db.commit()
        await self._record_event("error", message, "error")


def _share_of_voice_payload(result: PillarResult | None) -> dict[str, Any]:
    """Shape the Share of Voice findings for the API and the report."""
    if result is None:
        return {"tested": False, "skip_reason": "Not run.", "results": []}

    if result.skipped:
        return {
            "tested": False,
            "skip_reason": result.skip_reason,
            "prompts_tested": 0,
            "providers_tested": [],
            "total_calls": 0,
            "failed_calls": 0,
            "mention_rate": 0.0,
            "citation_rate": 0.0,
            "average_position": None,
            "sentiment_breakdown": {},
            "competitor_share": {},
            "results": [],
        }

    payload = dict(result.findings)
    payload.setdefault("tested", True)
    payload.setdefault("skip_reason", None)
    payload.setdefault("results", [])
    return payload


async def execute_audit(audit_id: uuid.UUID) -> None:
    await AuditRunner(audit_id).run()
