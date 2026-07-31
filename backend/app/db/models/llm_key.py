"""BYOK LLM API keys - stored encrypted, never returned in plaintext."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class LLMProviderName(enum.StrEnum):
    openai = "openai"
    anthropic = "anthropic"
    perplexity = "perplexity"


class LLMApiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "llm_api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[LLMProviderName] = mapped_column(
        Enum(LLMProviderName, name="llm_provider", native_enum=True), nullable=False
    )
    #: Fernet ciphertext. Decrypted in-memory only, inside the process making the
    #: LLM call, only for this user's own audit.
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    #: e.g. "sk-...ab12" - safe to show in the UI.
    key_preview: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(100), default="default", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Optional model override, e.g. "gpt-4o-mini". Falls back to adapter default.
    model: Mapped[str | None] = mapped_column(String(120))
    #: Ask the provider to answer with live web retrieval where it supports it.
    #: Grounded answers make citation rates comparable across providers.
    use_web_search: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="api_keys")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("user_id", "provider", "label", name="uq_llm_api_keys_user_provider_label"),
        Index("ix_llm_api_keys_user_id", "user_id"),
    )
