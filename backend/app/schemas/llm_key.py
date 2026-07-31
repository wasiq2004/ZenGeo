"""BYOK LLM API key schemas.

The raw key appears in exactly one place in this file - the create request.
Every response type carries only the masked preview.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.db.models.llm_key import LLMProviderName
from app.schemas.common import ORMModel, StrictModel


class LLMKeyCreate(StrictModel):
    provider: LLMProviderName
    #: Never stored or returned as-is; encrypted immediately on receipt.
    api_key: str = Field(min_length=8, max_length=500, repr=False)
    label: str = Field(default="default", min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=120)
    use_web_search: bool = True
    #: Verify the key against the provider before saving it.
    validate_before_save: bool = True

    @field_validator("api_key")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("API key cannot be blank")
        if any(ch.isspace() for ch in cleaned):
            raise ValueError("API keys do not contain spaces - check for a copy/paste error")
        return cleaned


class LLMKeyUpdate(StrictModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    use_web_search: bool | None = None


class LLMKeyPublic(ORMModel):
    """What the client sees. There is no field here that can reconstruct a key."""

    id: uuid.UUID
    provider: LLMProviderName
    label: str
    key_preview: str
    model: str | None
    is_active: bool
    use_web_search: bool
    last_validated_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class LLMKeyValidationResult(StrictModel):
    ok: bool
    message: str
    available_models: list[str] = Field(default_factory=list)


class LLMKeyCreateResponse(StrictModel):
    key: LLMKeyPublic
    validation: LLMKeyValidationResult | None = None


class ProviderInfo(StrictModel):
    name: str
    display_name: str
    default_model: str
    models: list[str]
    key_format_hint: str
    docs_url: str
    supports_web_search: bool
    always_grounded: bool
