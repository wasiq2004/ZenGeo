"""PDF report generation.

Rendered server-side from a Jinja2 template with WeasyPrint. Files are written
to a private volume and are never served statically - the download endpoint
checks ownership on every request.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.audit.pillars import PILLAR_WEIGHTS
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.audit import Audit
from app.db.session import SessionLocal

log = get_logger("report")

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    # Report data includes user-supplied text (business name, prompts, page
    # excerpts). Autoescaping keeps that out of the rendered markup.
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

PILLAR_ORDER = list(PILLAR_WEIGHTS)


def reports_dir() -> Path:
    path = Path(settings.reports_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_path(audit_id: uuid.UUID) -> Path:
    # Filename is derived from the UUID only - no user input reaches the path.
    return reports_dir() / f"{audit_id}.pdf"


def _safe_filename(business_name: str, audit_id: uuid.UUID) -> str:
    """A download filename that cannot escape a directory or break a header."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", business_name).strip("-").lower()[:60]
    return f"checkgeo-{slug or 'report'}-{str(audit_id)[:8]}.pdf"


def build_context(audit: Audit) -> dict[str, Any]:
    """Everything the template needs, already shaped for display."""
    pillar_scores: dict[str, Any] = audit.pillar_scores or {}
    pillars = [pillar_scores[key] for key in PILLAR_ORDER if key in pillar_scores]

    recommendations = audit.recommendations or []
    sov = audit.share_of_voice_results or {}
    score = float(audit.geo_score) if audit.geo_score is not None else 0.0

    generated_at = datetime.now(UTC)

    return {
        "business": audit.business,
        "generated_at": generated_at,
        # Computed here rather than in the template: Jinja has no timedelta, and
        # the fortnight is a judgement about how long schema and llms.txt take to
        # be re-crawled, which belongs in code where it can be explained.
        "recheck_at": generated_at + timedelta(days=14),
        "score": score,
        "band": audit.score_band or "Poor",
        "pillars": pillars,
        # Already ordered by impact, then effort, then pillar headroom
        # (scoring.prioritise_recommendations). The report takes the head of
        # this list rather than re-sorting, so page 4 and the dashboard can
        # never disagree about what comes first.
        "recommendations": recommendations,
        "recommendation_count": len(recommendations),
        "sov": sov,
        "sov_results": sov.get("results") or [],
    }


def _render_pdf(html: str, destination: Path) -> None:
    """Blocking WeasyPrint render. Called via a worker thread."""
    from weasyprint import HTML  # imported here so the API process never loads it

    HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf(str(destination))


async def generate_report(audit_id: uuid.UUID) -> Path:
    """Render the PDF for a completed audit and return its path."""
    async with SessionLocal() as db:
        audit = await db.scalar(
            select(Audit)
            .where(Audit.id == audit_id)
            .options(selectinload(Audit.business))
        )
        if audit is None:
            raise ValueError(f"Audit {audit_id} not found")
        context = build_context(audit)
        html = _env.get_template("report.html").render(**context)

    destination = report_path(audit_id)
    # WeasyPrint is CPU-bound and synchronous; keep it off the event loop.
    await asyncio.to_thread(_render_pdf, html, destination)

    log.info(
        "report_generated",
        audit_id=str(audit_id),
        bytes=destination.stat().st_size if destination.exists() else 0,
    )
    return destination


def delete_report_file(audit: Audit) -> None:
    """Remove a stored PDF. Safe to call when there is nothing to remove."""
    if not audit.pdf_report_path:
        return
    try:
        # Resolve against the reports directory rather than trusting the stored
        # string, so a tampered row cannot delete something else.
        path = report_path(audit.id)
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("report_delete_failed", audit_id=str(audit.id), error=str(exc))


def download_filename(audit: Audit) -> str:
    business_name = audit.business.name if audit.business else "report"
    return _safe_filename(business_name, audit.id)
