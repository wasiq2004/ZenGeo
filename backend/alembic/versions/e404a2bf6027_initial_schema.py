"""initial schema

Revision ID: e404a2bf6027
Revises: 
Create Date: 2026-07-30 05:11:54.469897
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision: str = 'e404a2bf6027'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users.email is CITEXT for case-insensitive uniqueness. The Docker init
    # script normally creates this extension; doing it here as well keeps the
    # migration self-contained for any other Postgres instance.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table('users',
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=True),
    sa.Column('role', sa.Enum('user', 'admin', name='user_role'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_email_verified', sa.Boolean(), nullable=False),
    sa.Column('mfa_secret', sa.Text(), nullable=True),
    sa.Column('mfa_enabled', sa.Boolean(), nullable=False),
    sa.Column('failed_login_count', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notify_audit_complete', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('admin_audit_log',
    sa.Column('admin_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('target_user_id', sa.UUID(), nullable=True),
    sa.Column('target_type', sa.String(length=40), nullable=True),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], name=op.f('fk_admin_audit_log_admin_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], name=op.f('fk_admin_audit_log_target_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_audit_log'))
    )
    op.create_index('ix_admin_audit_log_admin_user_id', 'admin_audit_log', ['admin_user_id'], unique=False)
    op.create_index('ix_admin_audit_log_created_at', 'admin_audit_log', ['created_at'], unique=False)
    op.create_index('ix_admin_audit_log_target_user_id', 'admin_audit_log', ['target_user_id'], unique=False)
    op.create_table('businesses',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('industry', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('target_audience', sa.Text(), nullable=True),
    sa.Column('location', sa.String(length=300), nullable=True),
    sa.Column('competitors', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('unique_selling_points', sa.Text(), nullable=True),
    sa.Column('website_url', sa.String(length=2000), nullable=False),
    sa.Column('key_pages', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('cms_platform', sa.String(length=120), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_businesses_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_businesses'))
    )
    op.create_index('ix_businesses_user_id', 'businesses', ['user_id'], unique=False)
    op.create_table('kpi_snapshots',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('audits_run', sa.Integer(), nullable=False),
    sa.Column('audits_completed', sa.Integer(), nullable=False),
    sa.Column('avg_geo_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_kpi_snapshots_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kpi_snapshots')),
    sa.UniqueConstraint('user_id', 'snapshot_date', name='uq_kpi_snapshots_user_id_date')
    )
    op.create_index('ix_kpi_snapshots_snapshot_date', 'kpi_snapshots', ['snapshot_date'], unique=False)
    op.create_table('llm_api_keys',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Enum('openai', 'anthropic', 'perplexity', name='llm_provider'), nullable=False),
    sa.Column('encrypted_key', sa.LargeBinary(), nullable=False),
    sa.Column('key_preview', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_llm_api_keys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_api_keys')),
    sa.UniqueConstraint('user_id', 'provider', 'label', name='uq_llm_api_keys_user_provider_label')
    )
    op.create_index('ix_llm_api_keys_user_id', 'llm_api_keys', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by', sa.UUID(), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index('ix_refresh_tokens_family_id', 'refresh_tokens', ['family_id'], unique=False)
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('user_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.Enum('email_verification', 'password_reset', name='token_purpose'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_tokens_token_hash'))
    )
    op.create_index('ix_user_tokens_user_id_purpose', 'user_tokens', ['user_id', 'purpose'], unique=False)
    op.create_table('audits',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='audit_status'), nullable=False),
    sa.Column('questionnaire_answers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pillar_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('geo_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('score_band', sa.String(length=20), nullable=True),
    sa.Column('share_of_voice_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('recommendations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('raw_findings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('pdf_report_path', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('progress', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_audits_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audits_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audits'))
    )
    op.create_index('ix_audits_status', 'audits', ['status'], unique=False)
    op.create_index('ix_audits_user_id', 'audits', ['user_id'], unique=False)
    op.create_index('ix_audits_user_id_created_at', 'audits', ['user_id', 'created_at'], unique=False)
    op.create_table('audit_events',
    sa.Column('audit_id', sa.UUID(), nullable=False),
    sa.Column('stage', sa.String(length=80), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['audit_id'], ['audits.id'], name=op.f('fk_audit_events_audit_id_audits'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index('ix_audit_events_audit_id', 'audit_events', ['audit_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_audit_events_audit_id', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_audits_user_id_created_at', table_name='audits')
    op.drop_index('ix_audits_user_id', table_name='audits')
    op.drop_index('ix_audits_status', table_name='audits')
    op.drop_table('audits')
    op.drop_index('ix_user_tokens_user_id_purpose', table_name='user_tokens')
    op.drop_table('user_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_family_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_llm_api_keys_user_id', table_name='llm_api_keys')
    op.drop_table('llm_api_keys')
    op.drop_index('ix_kpi_snapshots_snapshot_date', table_name='kpi_snapshots')
    op.drop_table('kpi_snapshots')
    op.drop_index('ix_businesses_user_id', table_name='businesses')
    op.drop_table('businesses')
    op.drop_index('ix_admin_audit_log_target_user_id', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_log_created_at', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_log_admin_user_id', table_name='admin_audit_log')
    op.drop_table('admin_audit_log')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    # ### end Alembic commands ###
