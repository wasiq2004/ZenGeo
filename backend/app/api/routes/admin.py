"""Admin panel endpoints.

Every route depends on `AdminUser`, which re-reads the user from the database
and checks the role on each request - a token minted before a demotion stops
working immediately. Every mutation is written to the admin audit log.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession, Pagination
from app.core.logging import get_logger
from app.core.rate_limit import RateLimit, client_ip
from app.core.security import create_access_token, verify_password
from app.db.models.analytics import AdminAuditLog
from app.db.models.audit import Audit, AuditStatus
from app.db.models.business import Business
from app.db.models.llm_key import LLMApiKey
from app.db.models.user import RefreshToken, User, UserRole
from app.schemas.admin import (
    AdminAuditRow,
    AdminLogEntry,
    AdminPasswordReset,
    AdminPasswordResetResult,
    AdminStats,
    AdminUserCreate,
    AdminUserRow,
    AdminUserUpdate,
    ImpersonateRequest,
    ImpersonateResult,
)
from app.schemas.auth import UserPublic
from app.schemas.common import Message, Page
from app.services import admin_log, auth_service

router = APIRouter(prefix="/admin", tags=["admin"])
log = get_logger("admin")

# Resetting someone else's password is the most sensitive thing an admin can
# do here, and it is the only account-recovery path, so it is rate-limited and
# written to the audit trail.
password_reset_limit = RateLimit("20/hour", scope="admin-password-reset")

# Impersonation is the most powerful thing here, so it is the most tightly
# limited: enough for a support session, not enough to sweep an account list.
impersonate_limit = RateLimit("10/hour", scope="admin-impersonate")

#: Deliberately far shorter than a normal access token. Impersonation is for
#: reproducing a problem, not for working as someone else all day.
IMPERSONATION_TTL = timedelta(minutes=30)


@router.get("/stats", response_model=AdminStats, summary="Platform-wide KPIs")
async def platform_stats(_: AdminUser, db: DbSession) -> AdminStats:
    now = datetime.now(UTC)
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    user_totals = (
        await db.execute(
            select(
                func.count(User.id),
                func.count(case((User.last_login_at >= month_ago, 1))),
                func.count(case((User.created_at >= week_ago, 1))),
            )
        )
    ).one()

    audit_totals = (
        await db.execute(
            select(
                func.count(Audit.id),
                func.count(case((func.date(Audit.created_at) == today, 1))),
                func.count(case((Audit.created_at >= week_ago, 1))),
                func.count(
                    case((Audit.status.in_([AuditStatus.pending, AuditStatus.running]), 1))
                ),
                func.count(
                    case(
                        ((Audit.status == AuditStatus.failed) & (Audit.created_at >= week_ago), 1)
                    )
                ),
                func.avg(case((Audit.status == AuditStatus.completed, Audit.geo_score))),
            )
        )
    ).one()

    provider_rows = await db.execute(
        select(LLMApiKey.provider, func.count(LLMApiKey.id))
        .where(LLMApiKey.is_active.is_(True))
        .group_by(LLMApiKey.provider)
    )
    provider_usage = {provider.value: count for provider, count in provider_rows}

    signups = await _daily_counts(db, User.created_at, days=30)
    audits = await _daily_counts(db, Audit.created_at, days=30)

    return AdminStats(
        total_users=user_totals[0] or 0,
        active_users_30d=user_totals[1] or 0,
        new_users_7d=user_totals[2] or 0,
        total_audits=audit_totals[0] or 0,
        audits_today=audit_totals[1] or 0,
        audits_7d=audit_totals[2] or 0,
        running_audits=audit_totals[3] or 0,
        failed_audits_7d=audit_totals[4] or 0,
        average_geo_score=round(float(audit_totals[5]), 1) if audit_totals[5] is not None else None,
        provider_usage=provider_usage,
        signups_trend=signups,
        audits_trend=audits,
    )


async def _daily_counts(db: DbSession, column: Any, *, days: int) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await db.execute(
        select(func.date(column), func.count()).where(column >= since).group_by(func.date(column))
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


def _user_row(user: User, audit_count: int, business_count: int, last_audit: datetime | None,
              providers: list[str]) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_email_verified=user.is_email_verified,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        audit_count=audit_count,
        business_count=business_count,
        api_key_providers=providers,
        last_audit_at=last_audit,
    )


@router.get("/users", response_model=Page[AdminUserRow], summary="All users")
async def list_users(
    _: AdminUser,
    db: DbSession,
    pagination: Pagination,
    search: str | None = Query(default=None, max_length=200),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> Page[AdminUserRow]:
    filters = []
    if search:
        # Parameterised by SQLAlchemy - the raw term never reaches the SQL text.
        term = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(term), User.full_name.ilike(term)))
    if role:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))

    total = await db.scalar(select(func.count()).select_from(User).where(*filters)) or 0

    audit_counts = (
        select(Audit.user_id, func.count(Audit.id).label("audit_count"),
               func.max(Audit.created_at).label("last_audit"))
        .group_by(Audit.user_id)
        .subquery()
    )
    business_counts = (
        select(Business.user_id, func.count(Business.id).label("business_count"))
        .group_by(Business.user_id)
        .subquery()
    )

    result = await db.execute(
        select(
            User,
            func.coalesce(audit_counts.c.audit_count, 0),
            func.coalesce(business_counts.c.business_count, 0),
            audit_counts.c.last_audit,
        )
        .outerjoin(audit_counts, audit_counts.c.user_id == User.id)
        .outerjoin(business_counts, business_counts.c.user_id == User.id)
        .where(*filters)
        .order_by(desc(User.created_at))
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    rows = result.all()

    user_ids = [row[0].id for row in rows]
    provider_map: dict[uuid.UUID, list[str]] = {}
    if user_ids:
        key_rows = await db.execute(
            select(LLMApiKey.user_id, LLMApiKey.provider)
            .where(LLMApiKey.user_id.in_(user_ids), LLMApiKey.is_active.is_(True))
            .distinct()
        )
        for user_id, provider in key_rows:
            provider_map.setdefault(user_id, []).append(provider.value)

    return Page[AdminUserRow](
        items=[
            _user_row(user, audit_count, business_count, last_audit, provider_map.get(user.id, []))
            for user, audit_count, business_count, last_audit in rows
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/users/{user_id}", summary="One user's detail")
async def user_detail(user_id: uuid.UUID, _: AdminUser, db: DbSession) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    businesses = list(await db.scalars(select(Business).where(Business.user_id == user_id)))
    audits = list(
        await db.scalars(
            select(Audit)
            .where(Audit.user_id == user_id)
            .options(selectinload(Audit.business))
            .order_by(Audit.created_at.desc())
            .limit(50)
        )
    )
    keys = list(await db.scalars(select(LLMApiKey).where(LLMApiKey.user_id == user_id)))

    # Counted in SQL, not as len(audits): that list is capped at 50, so a user
    # with 80 audits would otherwise be reported as having run exactly 50.
    totals = (
        await db.execute(
            select(
                func.count(Audit.id),
                func.count(case((Audit.status == AuditStatus.completed, 1))),
                func.count(case((Audit.status == AuditStatus.failed, 1))),
                func.count(case((Audit.pdf_report_path.is_not(None), 1))),
            ).where(Audit.user_id == user_id)
        )
    ).one()
    audits_total, audits_completed, audits_failed, reports_total = (t or 0 for t in totals)
    activity = list(
        await db.scalars(
            select(AdminAuditLog)
            .where(AdminAuditLog.target_user_id == user_id)
            .order_by(AdminAuditLog.created_at.desc())
            .limit(50)
        )
    )

    return {
        "user": _user_row(
            user,
            audits_total,
            len(businesses),
            audits[0].created_at if audits else None,
            sorted({key.provider.value for key in keys if key.is_active}),
        ).model_dump(mode="json"),
        "audit_summary": {
            "total": audits_total,
            "completed": audits_completed,
            "failed": audits_failed,
            "reports": reports_total,
            "showing": len(audits),
        },
        "businesses": [
            {
                "id": str(b.id),
                "name": b.name,
                "website_url": b.website_url,
                "industry": b.industry,
                "created_at": b.created_at.isoformat(),
            }
            for b in businesses
        ],
        "audits": [
            {
                "id": str(a.id),
                "business_name": a.business.name if a.business else "",
                "status": a.status.value,
                "geo_score": float(a.geo_score) if a.geo_score is not None else None,
                "score_band": a.score_band,
                "created_at": a.created_at.isoformat(),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                # Drives the download button. Admins may already fetch any
                # report via GET /reports/{id} - that route has allowed it all
                # along and logs the access - this only makes it visible.
                "has_report": bool(a.pdf_report_path),
            }
            for a in audits
        ],
        # Presence and provider only. The key itself is not readable here, and
        # there is no endpoint that would return it.
        "api_keys": [
            {
                "provider": key.provider.value,
                "label": key.label,
                "is_active": key.is_active,
                "created_at": key.created_at.isoformat(),
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            }
            for key in keys
        ],
        "admin_activity": [
            {
                "action": entry.action,
                "reason": entry.reason,
                "created_at": entry.created_at.isoformat(),
                "metadata": entry.meta,
            }
            for entry in activity
        ],
    }


@router.patch("/users/{user_id}", response_model=AdminUserRow, summary="Change role or status")
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    admin: AdminUser,
    db: DbSession,
    request: Request,
) -> AdminUserRow:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target.id == admin.id:
        # Prevents an admin locking themselves out or demoting the last admin
        # by accident. Another admin can still action it.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role or status. Ask another administrator.",
        )

    changes: dict[str, Any] = {}

    if payload.role is not None and payload.role != target.role:
        if target.role is UserRole.admin and payload.role is UserRole.user:
            remaining = await db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.admin, User.is_active.is_(True), User.id != target.id)
            )
            if not remaining:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This is the last active administrator. Promote someone else first.",
                )
        changes["role"] = {"from": target.role.value, "to": payload.role.value}
        target.role = payload.role

    if payload.is_active is not None and payload.is_active != target.is_active:
        changes["is_active"] = {"from": target.is_active, "to": payload.is_active}
        target.is_active = payload.is_active
        if not payload.is_active:
            # A disabled account must lose its sessions immediately, not at
            # the next access-token expiry.
            await auth_service.revoke_all_sessions(db, target.id)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to change"
        )

    await admin_log.record(
        db,
        admin_user_id=admin.id,
        action="user.update",
        target_user_id=target.id,
        target_type="user",
        target_id=str(target.id),
        reason=payload.reason,
        metadata=changes,
        ip_address=client_ip(request),
    )
    await db.commit()

    return _user_row(target, 0, 0, None, [])


@router.post("/users/{user_id}/force-logout", response_model=Message, summary="Revoke sessions")
async def force_logout(
    user_id: uuid.UUID, admin: AdminUser, db: DbSession, request: Request
) -> Message:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    count = await auth_service.revoke_all_sessions(db, target.id)
    await admin_log.record(
        db,
        admin_user_id=admin.id,
        action="user.force_logout",
        target_user_id=target.id,
        target_type="user",
        target_id=str(target.id),
        metadata={"sessions_revoked": count},
        ip_address=client_ip(request),
    )
    await db.commit()
    return Message(detail=f"Revoked {count} session(s) for {target.email}.")


@router.get("/audits", response_model=Page[AdminAuditRow], summary="All audits")
async def list_all_audits(
    _: AdminUser,
    db: DbSession,
    pagination: Pagination,
    search: str | None = Query(default=None, max_length=200),
    audit_status: AuditStatus | None = Query(default=None, alias="status"),
) -> Page[AdminAuditRow]:
    filters = []
    if audit_status:
        filters.append(Audit.status == audit_status)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(User.email.ilike(term), Business.name.ilike(term), Business.website_url.ilike(term))
        )

    base = (
        select(Audit, User.email, Business.name, Business.website_url)
        .join(User, User.id == Audit.user_id)
        .join(Business, Business.id == Audit.business_id)
        .where(*filters)
    )

    total = await db.scalar(
        select(func.count())
        .select_from(Audit)
        .join(User, User.id == Audit.user_id)
        .join(Business, Business.id == Audit.business_id)
        .where(*filters)
    ) or 0

    rows = await db.execute(
        base.order_by(Audit.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    return Page[AdminAuditRow](
        items=[
            AdminAuditRow(
                id=audit.id,
                user_id=audit.user_id,
                user_email=email,
                business_name=name,
                website_url=url,
                status=audit.status.value,
                geo_score=float(audit.geo_score) if audit.geo_score is not None else None,
                score_band=audit.score_band,
                created_at=audit.created_at,
                completed_at=audit.completed_at,
                error_message=audit.error_message,
            )
            for audit, email, name, url in rows
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/activity", response_model=Page[AdminLogEntry], summary="Admin action log")
async def activity_log(
    _: AdminUser, db: DbSession, pagination: Pagination
) -> Page[AdminLogEntry]:
    total = await db.scalar(select(func.count()).select_from(AdminAuditLog)) or 0

    admin_alias = select(User.id, User.email).subquery()
    target_alias = select(User.id, User.email).subquery()

    rows = await db.execute(
        select(AdminAuditLog, admin_alias.c.email, target_alias.c.email)
        .outerjoin(admin_alias, admin_alias.c.id == AdminAuditLog.admin_user_id)
        .outerjoin(target_alias, target_alias.c.id == AdminAuditLog.target_user_id)
        .order_by(AdminAuditLog.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    return Page[AdminLogEntry](
        items=[
            AdminLogEntry(
                id=entry.id,
                action=entry.action,
                admin_email=admin_email,
                target_user_id=entry.target_user_id,
                target_user_email=target_email,
                target_type=entry.target_type,
                target_id=entry.target_id,
                reason=entry.reason,
                metadata=entry.meta or {},
                created_at=entry.created_at,
            )
            for entry, admin_email, target_email in rows
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminPasswordResetResult,
    dependencies=[Depends(password_reset_limit)],
    summary="Set a new password for a user",
)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: AdminPasswordReset,
    admin: AdminUser,
    db: DbSession,
    request: Request,
) -> AdminPasswordResetResult:
    """Recover a locked-out account.

    This deployment sends no email, so there is no self-service "forgot
    password" link - this endpoint is the entire recovery path, and without it
    a forgotten password would mean a permanently unreachable account.

    The new password is returned exactly once, in this response, for the admin
    to hand over out of band. It is stored only as an Argon2 hash, so it cannot
    be read back afterwards. Every session the user had is revoked: if the
    reason for the reset was a compromise, leaving the attacker's refresh token
    alive would defeat the point.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such user")

    # Counted BEFORE the change, because set_password revokes the sessions
    # itself. Asking afterwards would always answer zero and the UI would
    # cheerfully report "0 sessions signed out" every single time.
    revoked = (
        await db.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        )
        or 0
    )
    await auth_service.set_password(db, user=user, new_password=payload.new_password)

    await admin_log.record(
        db,
        admin_user_id=admin.id,
        action="user.reset_password",
        target_type="user",
        target_id=str(user.id),
        # The password itself is never written to the audit trail.
        metadata={"sessions_revoked": revoked, "reason": payload.reason or None},
        ip_address=client_ip(request),
    )
    await db.commit()

    log.info(
        "admin_password_reset",
        admin_id=str(admin.id),
        user_id=str(user.id),
        sessions_revoked=revoked,
    )

    return AdminPasswordResetResult(
        email=user.email,
        new_password=payload.new_password,
        sessions_revoked=revoked,
        detail=(
            "Password updated and every existing session signed out. Give this "
            "password to the user over a channel you trust - it cannot be shown again."
        ),
    )


@router.post(
    "/users/{user_id}/impersonate",
    response_model=ImpersonateResult,
    dependencies=[Depends(impersonate_limit)],
    summary="Act as a user, to see what they see",
)
async def impersonate_user(
    user_id: uuid.UUID,
    payload: ImpersonateRequest,
    admin: AdminUser,
    db: DbSession,
    request: Request,
) -> ImpersonateResult:
    """Mint a short-lived token that authenticates AS the target user.

    The subject of the token is the target, so every ownership check, row
    filter and permission in the application behaves exactly as it does for
    that user - there is no parallel "admin view" code path that could drift
    out of step with the real one. What marks the session is an extra `act`
    claim naming the admin, which the API uses to refuse account-destructive
    actions and the UI uses to show a persistent banner.

    Three deliberate constraints:

    * The admin re-enters their own password. A borrowed or hijacked admin
      session is precisely what would otherwise become access to every account.
    * The token lives 30 minutes, not the usual access-token lifetime. It is
      for reproducing a problem, not for working as someone else all day.
    * Admins cannot impersonate other admins. Lateral movement between
      privileged accounts is the step that turns one compromise into a full
      takeover, and no support task needs it.
    """
    if not verify_password(payload.password, admin.password_hash):
        # Deliberately the same shape as a normal auth failure, and logged so
        # repeated attempts against this endpoint are visible.
        log.warning("impersonation_reauth_failed", admin_id=str(admin.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Password is incorrect"
        )

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such user")

    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already signed in as yourself.",
        )

    if target.role is UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot be impersonated.",
        )

    if not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That account is disabled. Re-enable it first.",
        )

    token, expires_in = create_access_token(
        user_id=target.id,
        role=target.role.value,
        email_verified=target.is_email_verified,
        expires_delta=IMPERSONATION_TTL,
        impersonated_by=admin.id,
    )

    await admin_log.record(
        db,
        admin_user_id=admin.id,
        action="user.impersonate",
        target_type="user",
        target_id=str(target.id),
        # The token itself is never recorded, here or in the application log.
        metadata={"ttl_seconds": int(IMPERSONATION_TTL.total_seconds()),
                  "reason": payload.reason or None},
        ip_address=client_ip(request),
    )
    await db.commit()

    log.info(
        "impersonation_started",
        admin_id=str(admin.id),
        target_user_id=str(target.id),
        ttl_seconds=int(IMPERSONATION_TTL.total_seconds()),
    )

    return ImpersonateResult(
        access_token=token,
        expires_in=expires_in,
        user=UserPublic.model_validate(target),
        impersonated_by=admin.id,
        detail=(
            f"Acting as {target.email} for the next "
            f"{int(IMPERSONATION_TTL.total_seconds() // 60)} minutes. Account changes "
            "are blocked while impersonating."
        ),
    )


@router.post(
    "/users",
    response_model=AdminUserRow,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account on someone's behalf",
)
async def create_user_account(
    payload: AdminUserCreate,
    admin: AdminUser,
    db: DbSession,
    request: Request,
) -> AdminUserRow:
    """Create an account directly, credentials and all.

    No mail leaves this deployment, so there is no invitation to send - the
    admin sets the password here and passes it on out of band, the same shape
    as the recovery flow in reset_user_password.

    Creating an administrator is permitted but recorded distinctly in the audit
    trail: it is the one action here that hands over the whole panel.
    """
    try:
        user = await auth_service.create_user(
            db,
            email=str(payload.email),
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except auth_service.EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc

    await admin_log.record(
        db,
        admin_user_id=admin.id,
        action="user.create_admin" if payload.role is UserRole.admin else "user.create",
        target_type="user",
        target_id=str(user.id),
        # The password is never written to the trail.
        metadata={"role": payload.role.value, "reason": payload.reason or None},
        ip_address=client_ip(request),
    )
    await db.commit()

    log.info(
        "admin_created_user",
        admin_id=str(admin.id),
        user_id=str(user.id),
        role=payload.role.value,
    )
    return _user_row(user, 0, 0, None, [])
