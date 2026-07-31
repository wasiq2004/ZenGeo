"""Profile and account-management schemas."""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.common import StrictModel


class ProfileUpdate(StrictModel):
    full_name: str | None = Field(default=None, max_length=200)
    notify_audit_complete: bool | None = None


class EmailChangeRequest(StrictModel):
    new_email: EmailStr
    #: Re-authentication: a hijacked session must not be able to move the
    #: account to an attacker-controlled address.
    password: str = Field(min_length=1, max_length=128)


class AccountDeleteRequest(StrictModel):
    password: str = Field(min_length=1, max_length=128)
    #: Typed confirmation, so an accidental click cannot destroy an account.
    confirmation: str = Field(min_length=6, max_length=20)
