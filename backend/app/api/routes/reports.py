"""Authenticated PDF report download.

Reports live on a private volume that is not served statically. Every download
re-checks that the requester owns the audit (or is an administrator), so a
guessed audit id gets a 404 rather than someone else's report.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.db.models.audit import Audit, AuditStatus
from app.db.models.user import UserRole
from app.services.report import download_filename, report_path

router = APIRouter(prefix="/reports", tags=["reports"])
log = get_logger("reports")


@router.get("/{audit_id}", summary="Download an audit's PDF report")
async def download_report(
    audit_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> FileResponse:
    audit = await db.scalar(
        select(Audit).where(Audit.id == audit_id).options(selectinload(Audit.business))
    )

    # Ownership is checked before existence is confirmed, so a non-owner cannot
    # distinguish "exists but not yours" from "does not exist".
    if audit is None or (audit.user_id != user.id and user.role is not UserRole.admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    if audit.status is not AuditStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This audit has not finished yet, so there is no report to download.",
        )

    path = report_path(audit.id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The report file is missing. Re-run the audit to regenerate it.",
        )

    if audit.user_id != user.id:
        log.info(
            "admin_report_access", admin_id=str(user.id), audit_id=str(audit.id)
        )

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=download_filename(audit),
        headers={
            # Reports contain business data; never let a proxy cache them.
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
        },
    )
