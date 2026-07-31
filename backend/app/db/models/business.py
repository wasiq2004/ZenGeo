"""Business / brand profiles being audited."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.audit import Audit
    from app.db.models.user import User


class Business(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "businesses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(300))
    competitors: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}", nullable=False
    )
    unique_selling_points: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    key_pages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}", nullable=False
    )
    cms_platform: Mapped[str | None] = mapped_column(String(120))

    user: Mapped["User"] = relationship(back_populates="businesses")  # noqa: F821
    audits: Mapped[list["Audit"]] = relationship(  # noqa: F821
        back_populates="business", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_businesses_user_id", "user_id"),)
