"""Add groq to the llm_provider enum

Revision ID: a1c7d4e92b30
Revises: 8c5e6d6df0f5
Create Date: 2026-08-03

`provider` is a native Postgres enum, so a new adapter is not purely Python -
the type itself has to learn the value or every insert fails with
"invalid input value for enum llm_provider".

Postgres cannot remove a value from an enum, so the downgrade cannot simply
undo this. It reassigns any rows still using `groq` before rebuilding the type
without it; without that step the rebuild would fail on a foreign key it cannot
cast, which is a worse thing to discover mid-rollback.
"""

from __future__ import annotations

from alembic import op

revision: str = "a1c7d4e92b30"
down_revision: str | None = "8c5e6d6df0f5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # IF NOT EXISTS keeps this idempotent - re-running a migration on a database
    # that already has the value should be a no-op, not an error.
    op.execute("ALTER TYPE llm_provider ADD VALUE IF NOT EXISTS 'groq'")


def downgrade() -> None:
    # Any key stored against groq cannot survive the value disappearing. Deleting
    # is the honest option: the alternative is silently relabelling someone's
    # Groq key as OpenAI, which would then fail to authenticate in a way nobody
    # could explain.
    op.execute("DELETE FROM llm_api_keys WHERE provider = 'groq'")
    op.execute("ALTER TYPE llm_provider RENAME TO llm_provider_old")
    op.execute("CREATE TYPE llm_provider AS ENUM ('openai', 'anthropic', 'perplexity')")
    op.execute(
        "ALTER TABLE llm_api_keys ALTER COLUMN provider "
        "TYPE llm_provider USING provider::text::llm_provider"
    )
    op.execute("DROP TYPE llm_provider_old")
