"""Admin action audit trail.

Every state-mutating admin action is recorded before the response is sent.
The log is append-only: there is no update or delete path anywhere in the
codebase, so an administrator cannot erase their own trail through the app.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.analytics import AdminAuditLog

log = get_logger("admin_log")


async def record(
    db: AsyncSession,
    *,
    admin_user_id: uuid.UUID,
    action: str,
    target_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_user_id=target_user_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        meta=metadata or {},
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()

    log.info(
        "admin_action",
        action=action,
        admin_user_id=str(admin_user_id),
        target_user_id=str(target_user_id) if target_user_id else None,
    )
