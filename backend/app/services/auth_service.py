"""Authentication business logic.

Kept out of the route layer so the same rules apply to any future caller (CLI,
admin tooling, tests) and so each rule has one place to live.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    dummy_verify,
    expiry,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.db.models.user import RefreshToken, TokenPurpose, User, UserRole, UserToken

log = get_logger("auth")


class AuthError(Exception):
    """Base class for expected authentication failures."""

    status_code = 401
    detail = "Authentication failed"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail


class InvalidCredentials(AuthError):
    # Deliberately identical for "no such user" and "wrong password" so the
    # response cannot be used to enumerate registered addresses.
    detail = "Incorrect email or password"


class AccountLocked(AuthError):
    status_code = 423
    detail = "Too many failed attempts. Try again later."


class AccountDisabled(AuthError):
    status_code = 403
    detail = "This account has been disabled. Contact support."


class MFARequired(AuthError):
    status_code = 401
    detail = "A two-factor authentication code is required"


class EmailAlreadyRegistered(AuthError):
    status_code = 409
    detail = "An account with that email already exists"


class InvalidToken(AuthError):
    status_code = 400
    detail = "This link is invalid or has expired"


# --------------------------------------------------------------------------- #
# Signup
# --------------------------------------------------------------------------- #
async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    role: UserRole = UserRole.user,
    email_verified: bool = False,
) -> User:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        raise EmailAlreadyRegistered()

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        # Role is never taken from the signup request body - self-promotion to
        # admin has to be impossible by construction.
        role=role,
        is_email_verified=email_verified,
    )
    db.add(user)
    await db.flush()
    log.info("user_created", user_id=str(user.id), role=role.value)
    return user


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
async def authenticate(
    db: AsyncSession, *, email: str, password: str, totp_code: str | None
) -> User:
    user = await db.scalar(select(User).where(User.email == email))

    if user is None:
        dummy_verify()  # equalise response time with the "wrong password" path
        raise InvalidCredentials()

    now = datetime.now(UTC)
    if user.locked_until and user.locked_until > now:
        raise AccountLocked(
            "Too many failed attempts. Try again in "
            f"{int((user.locked_until - now).total_seconds() // 60) + 1} minutes."
        )

    if not verify_password(password, user.password_hash):
        await _register_failed_login(db, user)
        raise InvalidCredentials()

    if not user.is_active:
        raise AccountDisabled()

    if user.mfa_enabled:
        from app.services.mfa import verify_totp  # local import: optional feature

        if not totp_code:
            raise MFARequired()
        if not verify_totp(user, totp_code):
            await _register_failed_login(db, user)
            raise InvalidCredentials("Incorrect two-factor code")

    # Successful login: clear the lockout counters and opportunistically upgrade
    # the password hash if the Argon2 parameters have been strengthened.
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await db.flush()
    return user


async def _register_failed_login(db: AsyncSession, user: User) -> None:
    """Count the failure and lock the account once the threshold is crossed.

    Backs off exponentially: each lockout after the first lasts twice as long,
    capped at 24 hours.
    """
    user.failed_login_count += 1
    if user.failed_login_count >= settings.login_max_attempts:
        overflow = user.failed_login_count - settings.login_max_attempts
        seconds = min(settings.login_lockout_seconds * (2**overflow), 86_400)
        user.locked_until = expiry(minutes=seconds / 60)
        log.warning(
            "account_locked",
            user_id=str(user.id),
            failed_attempts=user.failed_login_count,
            lockout_seconds=seconds,
        )
    await db.flush()


# --------------------------------------------------------------------------- #
# Refresh tokens: rotation with reuse detection
# --------------------------------------------------------------------------- #
async def issue_refresh_token(
    db: AsyncSession,
    *,
    user: User,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    raw = generate_opaque_token(32)
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=expiry(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:300] or None,
        ip_address=(ip_address or "")[:64] or None,
    )
    db.add(record)
    await db.flush()
    return raw


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    raw_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str]:
    """Exchange a refresh token for a fresh one.

    Reuse detection: presenting a token that was already rotated means a copy
    leaked, so the entire family is revoked and the session is killed. The
    legitimate user simply logs in again; the attacker's stolen token is dead.
    """
    record = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if record is None:
        raise InvalidToken("Session expired. Please sign in again.")

    now = datetime.now(UTC)

    if record.revoked_at is not None:
        await _revoke_family(db, record.family_id)
        log.warning(
            "refresh_token_reuse_detected",
            user_id=str(record.user_id),
            family_id=str(record.family_id),
        )
        raise InvalidToken("Session expired. Please sign in again.")

    if record.expires_at <= now:
        raise InvalidToken("Session expired. Please sign in again.")

    user = await db.get(User, record.user_id)
    if user is None or not user.is_active:
        await _revoke_family(db, record.family_id)
        raise AccountDisabled()

    new_raw = await issue_refresh_token(
        db,
        user=user,
        family_id=record.family_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    successor = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(new_raw))
    )
    record.revoked_at = now
    record.replaced_by = successor.id if successor else None
    await db.flush()
    return user, new_raw


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    record = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if record and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        await db.flush()


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.flush()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Force-logout every device. Used on password change and by admins."""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.flush()
    # Only a CursorResult carries rowcount; an UPDATE always produces one, but
    # the static type is the broader Result.
    return int(getattr(result, "rowcount", 0) or 0)


# --------------------------------------------------------------------------- #
# One-shot email tokens
# --------------------------------------------------------------------------- #
async def create_user_token(
    db: AsyncSession, *, user: User, purpose: TokenPurpose
) -> str:
    """Issue a single-use token, invalidating any outstanding one of the same kind."""
    await db.execute(
        update(UserToken)
        .where(
            UserToken.user_id == user.id,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
    )
    raw = generate_opaque_token(32)
    ttl = (
        {"hours": settings.email_token_ttl_hours}
        if purpose is TokenPurpose.email_verification
        else {"minutes": settings.password_reset_ttl_minutes}
    )
    db.add(
        UserToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            purpose=purpose,
            expires_at=expiry(**ttl),
        )
    )
    await db.flush()
    return raw


async def consume_user_token(
    db: AsyncSession, *, raw_token: str, purpose: TokenPurpose
) -> User:
    record = await db.scalar(
        select(UserToken).where(
            UserToken.token_hash == hash_token(raw_token), UserToken.purpose == purpose
        )
    )
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise InvalidToken()

    user = await db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise InvalidToken()

    record.used_at = now
    await db.flush()
    return user


async def set_password(db: AsyncSession, *, user: User, new_password: str) -> None:
    """Change a password and invalidate every existing session."""
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    await db.flush()
    await revoke_all_sessions(db, user.id)
    log.info("password_changed", user_id=str(user.id))
