"""Rollups for dashboards and the tamper-evident admin action log."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KpiSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Daily per-user rollup so dashboards avoid scanning the audits table."""

    __tablename__ = "kpi_snapshots"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    audits_run: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    audits_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_geo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_kpi_snapshots_user_id_date"),
        Index("ix_kpi_snapshots_snapshot_date", "snapshot_date"),
    )


class AdminAuditLog(Base, UUIDPrimaryKeyMixin):
    """Every state-mutating admin action. Append-only; never updated or deleted."""

    __tablename__ = "admin_audit_log"

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_admin_audit_log_admin_user_id", "admin_user_id"),
        Index("ix_admin_audit_log_target_user_id", "target_user_id"),
        Index("ix_admin_audit_log_created_at", "created_at"),
    )
