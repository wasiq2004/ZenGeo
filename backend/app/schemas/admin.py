"""Admin panel schemas.

Note what is absent: there is no field anywhere here that exposes a user's LLM
API key. Administrators can see that a key exists and which provider it is for,
which is what support work needs, and nothing more.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import EmailStr, Field, field_validator

from app.db.models.user import UserRole
from app.schemas.auth import MIN_PASSWORD_LENGTH, UserPublic, validate_password_strength
from app.schemas.common import ORMModel, StrictModel


class AdminPasswordReset(StrictModel):
    """A new password chosen by an administrator for a locked-out user.

    The admin supplies the value rather than the server generating one, so it
    can be read out over whatever channel is already trusted (a call, a chat)
    without a second system holding a copy.
    """

    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    #: Free-text note written to the admin audit trail.
    reason: str = Field(default="", max_length=300)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        return validate_password_strength(v)


class AdminPasswordResetResult(StrictModel):
    email: str
    #: Echoed back exactly once so the admin can pass it on. Stored only as an
    #: Argon2 hash, so there is no way to retrieve it later.
    new_password: str
    sessions_revoked: int
    detail: str


class AdminUserRow(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    is_email_verified: bool
    mfa_enabled: bool
    created_at: datetime
    last_login_at: datetime | None

    audit_count: int = 0
    business_count: int = 0
    #: Providers with a key connected. Never the keys themselves.
    api_key_providers: list[str] = Field(default_factory=list)
    last_audit_at: datetime | None = None


class AdminUserCreate(StrictModel):
    """An account created by an administrator rather than by signup.

    The password is set here and handed over out of band - there is no mail
    transport to send an invitation with, so an admin-created account has to
    arrive with credentials already in it.
    """

    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole = UserRole.user
    reason: str = Field(default="", max_length=300)

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        return validate_password_strength(v)


class AdminUserUpdate(StrictModel):
    role: UserRole | None = None
    is_active: bool | None = None
    #: Recorded in the admin audit log alongside the change.
    reason: str | None = Field(default=None, max_length=500)


class AdminLogEntry(StrictModel):
    id: uuid.UUID
    action: str
    admin_email: str | None
    target_user_id: uuid.UUID | None
    target_user_email: str | None
    target_type: str | None
    target_id: str | None
    reason: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AdminStats(StrictModel):
    total_users: int
    active_users_30d: int
    new_users_7d: int
    total_audits: int
    audits_today: int
    audits_7d: int
    running_audits: int
    failed_audits_7d: int
    average_geo_score: float | None
    provider_usage: dict[str, int]
    signups_trend: list[dict[str, Any]]
    audits_trend: list[dict[str, Any]]


class AdminAuditRow(StrictModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    business_name: str
    website_url: str
    status: str
    geo_score: float | None
    score_band: str | None
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None


AdminUserSort = Literal["created_at", "last_login_at", "email", "audit_count"]


class ImpersonateRequest(StrictModel):
    """An admin's own password, re-confirmed before acting as someone else.

    Re-authentication is required because a stolen or borrowed admin session is
    exactly the thing impersonation would turn into full account access.
    """

    password: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=300)


class ImpersonateResult(StrictModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - the OAuth scheme name, not a secret
    expires_in: int
    #: Who the admin is now acting as.
    user: UserPublic
    impersonated_by: uuid.UUID
    detail: str


class AdminUserDelete(StrictModel):
    """Typed confirmation for an irreversible deletion.

    The admin retypes the account's email. A checkbox is too easy to click by
    reflex for something that cascades through every audit and report the user
    ever produced.
    """

    confirm_email: str = Field(min_length=3, max_length=320)
    reason: str = Field(default="", max_length=300)


class AdminUserDeleteResult(StrictModel):
    email: str
    audits_deleted: int
    businesses_deleted: int
    reports_removed: int
    detail: str
