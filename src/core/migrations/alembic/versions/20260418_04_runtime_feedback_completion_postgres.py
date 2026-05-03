\
"""postgres runtime baseline for feedback/completion outcomes

Revision ID: 20260418_04_runtime_feedback_completion_postgres
Revises: 20260414_03_runtime_pg_base
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260418_04_runtime_feedback_completion_postgres'
down_revision = '20260414_03_runtime_pg_base'
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())

def upgrade() -> None:
    op.create_table(
        'feedback_events_v1',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('feedback_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('recommendation_id', sa.Text(), nullable=False),
        sa.Column('decision', sa.Text(), nullable=False),
        sa.Column('reason_code', sa.Text(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('recommendation_created_at', sa.Text(), nullable=True),
        sa.Column('decision_seconds', sa.Integer(), nullable=True),
        sa.Column('related_alert', sa.Text(), nullable=True),
        sa.Column('task_id', sa.Text(), nullable=True),
        sa.Column('object_type', sa.Text(), nullable=True),
        sa.Column('object_id', sa.Text(), nullable=True),
        sa.Column('farm_id', sa.Text(), nullable=True),
        sa.Column('group_id', sa.Text(), nullable=True),
        sa.Column('data_version', sa.Text(), nullable=True),
        sa.Column('model_version', sa.Text(), nullable=True),
        sa.Column('report_version', sa.Text(), nullable=True),
        sa.Column('qc_run', sa.Text(), nullable=True),
        sa.Column('scoring_run', sa.Text(), nullable=True),
        sa.Column('feedback_source', sa.Text(), nullable=True),
        sa.Column('decision_id', sa.Text(), nullable=True),
        sa.Column('metadata_json', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("decision IN ('accepted','rejected')", name='ck_feedback_events_v1_decision'),
    )
    op.create_index('idx_feedback_v1_tenant_created', 'feedback_events_v1', ['tenant_id', sa.text('created_at DESC')])
    op.create_index('idx_feedback_v1_rec', 'feedback_events_v1', ['tenant_id', 'recommendation_id', sa.text('created_at DESC')])
    op.create_index('idx_feedback_v1_object', 'feedback_events_v1', ['tenant_id', 'object_type', 'object_id', sa.text('created_at DESC')])
    op.create_index('idx_feedback_v1_data_version', 'feedback_events_v1', ['tenant_id', 'data_version', sa.text('created_at DESC')])

    op.create_table(
        'completion_outcomes_v1',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('outcome_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('worklist_id', sa.Text(), nullable=True),
        sa.Column('task_id', sa.Text(), nullable=True),
        sa.Column('linked_decision_id', sa.Text(), nullable=True),
        sa.Column('related_alert', sa.Text(), nullable=True),
        sa.Column('object_type', sa.Text(), nullable=True),
        sa.Column('object_id', sa.Text(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('assignee_team', sa.Text(), nullable=True),
        sa.Column('worklist_type', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('due_at', sa.Text(), nullable=True),
        sa.Column('outcome_status', sa.Text(), nullable=False),
        sa.Column('reason_code', sa.Text(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('outcome_by', sa.Integer(), nullable=True),
        sa.Column('outcome_by_username', sa.Text(), nullable=True),
        sa.Column('outcome_role', sa.Text(), nullable=True),
        sa.Column('request_id', sa.Text(), nullable=True),
        sa.Column('data_version', sa.Text(), nullable=True),
        sa.Column('qc_run', sa.Text(), nullable=True),
        sa.Column('model_version', sa.Text(), nullable=True),
        sa.Column('scoring_run', sa.Text(), nullable=True),
        sa.Column('report_version', sa.Text(), nullable=True),
        sa.Column('metrics_json', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('auto_actions_json', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("outcome_status IN ('done','cancelled','deferred','no_effect','escalated')", name='ck_completion_outcomes_v1_status'),
    )
    op.create_index('idx_completion_outcomes_v1_task', 'completion_outcomes_v1', ['tenant_id', 'task_id', sa.text('created_at DESC')])
    op.create_index('idx_completion_outcomes_v1_worklist', 'completion_outcomes_v1', ['tenant_id', 'worklist_id', sa.text('created_at DESC')])
    op.create_index('idx_completion_outcomes_v1_status', 'completion_outcomes_v1', ['tenant_id', 'outcome_status', sa.text('created_at DESC')])
    op.create_index('idx_completion_outcomes_v1_alert', 'completion_outcomes_v1', ['tenant_id', 'related_alert', sa.text('created_at DESC')])
    op.create_index('idx_completion_outcomes_v1_decision', 'completion_outcomes_v1', ['tenant_id', 'linked_decision_id', sa.text('created_at DESC')])
    op.create_index('idx_completion_outcomes_v1_object', 'completion_outcomes_v1', ['tenant_id', 'object_type', 'object_id', sa.text('created_at DESC')])
    op.create_index('idx_completion_outcomes_v1_team', 'completion_outcomes_v1', ['tenant_id', 'assignee_team', sa.text('created_at DESC')])

def downgrade() -> None:
    for index_name, table_name in [
        ('idx_completion_outcomes_v1_team', 'completion_outcomes_v1'),
        ('idx_completion_outcomes_v1_object', 'completion_outcomes_v1'),
        ('idx_completion_outcomes_v1_decision', 'completion_outcomes_v1'),
        ('idx_completion_outcomes_v1_alert', 'completion_outcomes_v1'),
        ('idx_completion_outcomes_v1_status', 'completion_outcomes_v1'),
        ('idx_completion_outcomes_v1_worklist', 'completion_outcomes_v1'),
        ('idx_completion_outcomes_v1_task', 'completion_outcomes_v1'),
        ('idx_feedback_v1_data_version', 'feedback_events_v1'),
        ('idx_feedback_v1_object', 'feedback_events_v1'),
        ('idx_feedback_v1_rec', 'feedback_events_v1'),
        ('idx_feedback_v1_tenant_created', 'feedback_events_v1'),
    ]:
        op.drop_index(index_name, table_name=table_name)
    op.drop_table('completion_outcomes_v1')
    op.drop_table('feedback_events_v1')
