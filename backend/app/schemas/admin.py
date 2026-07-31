"""Admin panel schemas.

Note what is absent: there is no field anywhere here that exposes a user's LLM
API key. Administrators can see that a key exists and which provider it is for,
which is what support work needs, and nothing more.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import EmailStr, Field

from app.db.models.user import UserRole
from app.schemas.common import ORMModel, StrictModel


class EmailTestRequest(StrictModel):
    """Where to send the deliverability probe.

    Optional: omitted, it goes to the calling administrator's own address,
    which is the safe default. Allowing an arbitrary recipient is what makes
    this endpoint worth rate-limiting and audit-logging.
    """

    to: EmailStr | None = None


class EmailTestResult(StrictModel):
    delivered: bool
    backend: Literal["resend", "smtp", "console"]
    to: str
    mail_from: str
    sending_domain: str
    #: Resend's message id, when the provider returned one.
    provider_message_id: str | None = None
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
