"""Authentication request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.db.models.user import UserRole
from app.schemas.common import ORMModel, StrictModel

MIN_PASSWORD_LENGTH = 12

#: Passwords that meet the length rule but are still trivially guessable.
_WEAK_PASSWORDS = {
    "password1234",
    "passwordpassword",
    "123456789012",
    "qwertyuiop12",
    "administrator",
    "letmeinplease",
    "welcome12345",
    "iloveyou1234",
    "changemenow1",
}


def validate_password_strength(value: str) -> str:
    """Length-first policy.

    Modern guidance (NIST SP 800-63B) favours length and a blocklist over
    composition rules that push people towards `Passw0rd!`.
    """
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value) > 128:
        raise ValueError("Password must be at most 128 characters")
    if value.lower() in _WEAK_PASSWORDS:
        raise ValueError("That password is too common. Choose something less guessable.")
    if len(set(value)) < 5:
        raise ValueError("Password is too repetitive")
    return value


class SignupRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return validate_password_strength(v)


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    #: Required only when the account has TOTP enabled.
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class TokenResponse(StrictModel):
    """The refresh token is NOT in this body - it is set as an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - the OAuth scheme name, not a secret
    expires_in: int
    user: UserPublic


class SessionState(StrictModel):
    """Who you are, plus whether an admin is currently acting as you.

    `impersonated_by` is read from the token's `act` claim rather than stored,
    so it cannot drift from the credential actually presented.
    """

    user: UserPublic
    impersonated_by: uuid.UUID | None = None


class UserPublic(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    is_email_verified: bool
    mfa_enabled: bool
    notify_audit_complete: bool
    created_at: datetime
    last_login_at: datetime | None


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return validate_password_strength(v)


class MFASetupResponse(StrictModel):
    secret: str
    otpauth_uri: str


class MFAActivateRequest(StrictModel):
    code: str = Field(min_length=6, max_length=8)


class MFADisableRequest(StrictModel):
    password: str = Field(min_length=1, max_length=128)


TokenResponse.model_rebuild()
