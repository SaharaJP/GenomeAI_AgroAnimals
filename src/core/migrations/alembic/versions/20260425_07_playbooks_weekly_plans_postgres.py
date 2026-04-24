"""postgres: playbook_versions, playbooks_active, weekly_plans_v1, audit_archive_runs, collaboration_notes_v1

Revision ID: 20260425_07_playbooks_weekly_plans_postgres
Revises: 20260422_05_insights_table_postgres, 20260423_06_weekly_briefs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260425_07_playbooks_weekly_plans_postgres'
down_revision = ('20260422_05_insights_table_postgres', '20260423_06_weekly_briefs')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'playbook_versions',
        sa.Column('version_id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('playbook_key', sa.Text(), nullable=False),
        sa.Column('target_kind', sa.Text(), nullable=False),
        sa.Column('target_type', sa.Text(), nullable=False),
        sa.Column('farm_id', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps_json', sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_by_username', sa.Text(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.CheckConstraint("target_kind IN ('alert','task')", name='ck_playbook_versions_target_kind'),
    )
    op.create_index('idx_playbook_versions_key', 'playbook_versions', ['tenant_id', 'playbook_key', 'farm_id', sa.text('created_at DESC')])
    op.create_index('idx_playbook_versions_target', 'playbook_versions', ['tenant_id', 'target_kind', 'target_type', 'farm_id'])

    op.create_table(
        'playbooks_active',
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('playbook_key', sa.Text(), nullable=False),
        sa.Column('farm_id', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('active_version_id', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id', 'playbook_key', 'farm_id', name='pk_playbooks_active'),
    )

    op.create_table(
        'weekly_plans_v1',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('plan_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column('week_start', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('farm_id', sa.Text(), nullable=True),
        sa.Column('data_version', sa.Text(), nullable=True),
        sa.Column('action_items_json', sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_by_username', sa.Text(), nullable=False),
        sa.Column('approved_at', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_by_username', sa.Text(), nullable=True),
        sa.Column('approval_comment', sa.Text(), nullable=True),
        sa.Column('rejected_at', sa.Text(), nullable=True),
        sa.Column('rejected_by', sa.Integer(), nullable=True),
        sa.Column('rejected_by_username', sa.Text(), nullable=True),
        sa.Column('rejection_comment', sa.Text(), nullable=True),
        sa.Column('archived_at', sa.Text(), nullable=True),
        sa.Column('archived_by', sa.Integer(), nullable=True),
        sa.Column('archived_by_username', sa.Text(), nullable=True),
        sa.Column('archive_comment', sa.Text(), nullable=True),
        sa.Column('tasks_created_at', sa.Text(), nullable=True),
        sa.Column('tasks_created_run_id', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('draft','approved','archived')", name='ck_weekly_plans_v1_status'),
    )
    op.create_index('idx_weekly_plans_tenant_status', 'weekly_plans_v1', ['tenant_id', 'status'])

    op.create_table(
        'audit_archive_runs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('batch_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('cutoff_ts', sa.Text(), nullable=False),
        sa.Column('rows_archived', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
    )
    op.create_index('idx_audit_archive_runs_tenant_ts', 'audit_archive_runs', ['tenant_id', sa.text('created_at DESC')])

    op.create_table(
        'collaboration_notes_v1',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('note_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('object_type', sa.Text(), nullable=False),
        sa.Column('object_id', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('author_username', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=True),
        sa.Column('deleted_at', sa.Text(), nullable=True),
        sa.Column('pinned', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )
    op.create_index('idx_collab_notes_object', 'collaboration_notes_v1', ['tenant_id', 'object_type', 'object_id', sa.text('created_at DESC')])


def downgrade() -> None:
    for index_name, table_name in [
        ('idx_collab_notes_object', 'collaboration_notes_v1'),
        ('idx_audit_archive_runs_tenant_ts', 'audit_archive_runs'),
        ('idx_weekly_plans_tenant_status', 'weekly_plans_v1'),
        ('idx_playbook_versions_target', 'playbook_versions'),
        ('idx_playbook_versions_key', 'playbook_versions'),
    ]:
        op.drop_index(index_name, table_name=table_name)
    op.drop_table('collaboration_notes_v1')
    op.drop_table('audit_archive_runs')
    op.drop_table('weekly_plans_v1')
    op.drop_table('playbooks_active')
    op.drop_table('playbook_versions')
