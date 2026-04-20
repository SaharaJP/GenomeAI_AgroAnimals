"""auth runtime postgres baseline

Revision ID: 20260414_02_auth_pg_base
Revises: 
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260414_02_auth_pg_base'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'auth_users',
        sa.Column('user_id', sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('external_org', sa.Text(), nullable=True),
        sa.Column('collaboration_mode', sa.Text(), nullable=True),
        sa.Column('allowed_farm_ids_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('allowed_site_ids_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.Text(), nullable=False),
    )
    op.create_index('idx_auth_users_tenant_username', 'auth_users', ['tenant_id', 'username'], unique=True)

    op.create_table(
        'auth_sessions',
        sa.Column('session_id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('user_source', sa.Text(), nullable=False),
        sa.Column('client_kind', sa.Text(), nullable=False),
        sa.Column('auth_transport', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column('last_seen_at', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.Text(), nullable=True),
        sa.Column('refresh_expires_at', sa.Text(), nullable=True),
        sa.Column('access_token_hash', sa.Text(), nullable=True),
        sa.Column('refresh_token_hash', sa.Text(), nullable=True),
        sa.Column('device_id', sa.Text(), nullable=True),
        sa.Column('device_label', sa.Text(), nullable=True),
        sa.Column('device_platform', sa.Text(), nullable=True),
        sa.Column('device_app_version', sa.Text(), nullable=True),
        sa.Column('active_farm_id', sa.Text(), nullable=True),
        sa.Column('active_site_id', sa.Text(), nullable=True),
        sa.Column('allowed_farm_ids_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('allowed_site_ids_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('last_ip', sa.Text(), nullable=True),
        sa.Column('last_user_agent', sa.Text(), nullable=True),
        sa.Column('revoked_at', sa.Text(), nullable=True),
        sa.Column('revoke_reason', sa.Text(), nullable=True),
    )
    op.create_index('idx_auth_sessions_tenant_user', 'auth_sessions', ['tenant_id', 'user_id'])
    op.create_index('idx_auth_sessions_tenant_status', 'auth_sessions', ['tenant_id', 'status'])
    op.create_index('idx_auth_sessions_access_hash', 'auth_sessions', ['access_token_hash'], unique=True)
    op.create_index('idx_auth_sessions_refresh_hash', 'auth_sessions', ['refresh_token_hash'], unique=True)

    op.create_table(
        'auth_session_refresh_lineage',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('previous_refresh_token_hash', sa.Text(), nullable=True),
        sa.Column('new_refresh_token_hash', sa.Text(), nullable=True),
        sa.Column('rotated_at', sa.Text(), nullable=False),
        sa.Column('device_app_version', sa.Text(), nullable=True),
    )
    op.create_index('idx_auth_refresh_lineage_session', 'auth_session_refresh_lineage', ['session_id', 'rotated_at'])

    op.create_table(
        'auth_failed_attempts',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('reason_code', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('ip', sa.Text(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
    )
    op.create_index('idx_auth_failed_attempts_tenant_created', 'auth_failed_attempts', ['tenant_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_auth_failed_attempts_tenant_created', table_name='auth_failed_attempts')
    op.drop_table('auth_failed_attempts')
    op.drop_index('idx_auth_refresh_lineage_session', table_name='auth_session_refresh_lineage')
    op.drop_table('auth_session_refresh_lineage')
    op.drop_index('idx_auth_sessions_refresh_hash', table_name='auth_sessions')
    op.drop_index('idx_auth_sessions_access_hash', table_name='auth_sessions')
    op.drop_index('idx_auth_sessions_tenant_status', table_name='auth_sessions')
    op.drop_index('idx_auth_sessions_tenant_user', table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_index('idx_auth_users_tenant_username', table_name='auth_users')
    op.drop_table('auth_users')
