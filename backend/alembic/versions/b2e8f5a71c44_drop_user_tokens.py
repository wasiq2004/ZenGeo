"""Drop the orphaned user_tokens table and token_purpose enum

Revision ID: b2e8f5a71c44
Revises: a1c7d4e92b30
Create Date: 2026-08-03

`user_tokens` held single-use links for email verification and password reset.
Both flows were removed when this deployment stopped sending mail, and nothing
has written to or read from the table since - it is a table and a Postgres enum
type that no code path can reach.

Rows are deliberately not preserved. Every one of them is a hash of a link that
was already single-use and short-lived, and none can be redeemed now that the
endpoints are gone.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2e8f5a71c44"
down_revision: str | None = "a1c7d4e92b30"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_index("ix_user_tokens_user_id_purpose", table_name="user_tokens")
    op.drop_table("user_tokens")
    # The enum is not dropped with the table - Postgres keeps the type around,
    # and leaving it behind is exactly the kind of debris this migration exists
    # to remove.
    op.execute("DROP TYPE IF EXISTS token_purpose")


def downgrade() -> None:
    token_purpose = postgresql.ENUM(
        "email_verification", "password_reset", name="token_purpose", create_type=False
    )
    token_purpose.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "user_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("purpose", token_purpose, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "ix_user_tokens_user_id_purpose", "user_tokens", ["user_id", "purpose"]
    )
