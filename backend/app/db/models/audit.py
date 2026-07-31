"""Audit runs, their scores, and the per-stage progress log."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.business import Business


class AuditStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Audit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status", native_enum=True),
        default=AuditStatus.pending,
        nullable=False,
    )

    questionnaire_answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    #: {"crawlability": {"score": 82, "findings": [...]}, ...}
    pillar_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    geo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    score_band: Mapped[str | None] = mapped_column(String(20))
    #: Per-prompt, per-provider Share of Voice results.
    share_of_voice_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recommendations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    #: Everything the engine actually observed - shown in the PDF appendix.
    raw_findings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    pdf_report_path: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    #: 0-100, updated as pillars finish so the UI can show a progress bar.
    progress: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    business: Mapped["Business"] = relationship(back_populates="audits")  # noqa: F821
    events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="audit",
        cascade="all, delete-orphan",
        order_by="AuditEvent.created_at",
    )

    __table_args__ = (
        Index("ix_audits_user_id", "user_id"),
        Index("ix_audits_status", "status"),
        Index("ix_audits_user_id_created_at", "user_id", "created_at"),
    )


class AuditEvent(Base, UUIDPrimaryKeyMixin):
    """Append-only progress / debugging log for a single audit."""

    __tablename__ = "audit_events"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    audit: Mapped[Audit] = relationship(back_populates="events")

    __table_args__ = (Index("ix_audit_events_audit_id", "audit_id"),)
