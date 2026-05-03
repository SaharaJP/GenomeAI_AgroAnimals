"""postgres: timeline_events table

Revision ID: 20260426_09_timeline_events
Revises: 20260425_08_weekly_plans_approval_requested_at
"""

from alembic import op
import sqlalchemy as sa

revision = '20260426_09_timeline_events'
down_revision = '20260425_08_weekly_plans_approval_requested_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'timeline_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('timeline_event_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False, server_default=sa.text("'default'")),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True, server_default=sa.text("''")),
        sa.Column('event_date', sa.Text(), nullable=False),
        sa.Column('animal_ids', sa.Text(), nullable=True, server_default=sa.text("'[]'")),
        sa.Column('affected_groups', sa.Text(), nullable=True, server_default=sa.text("'[]'")),
        sa.Column('source', sa.Text(), nullable=True, server_default=sa.text("'user'")),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_by_username', sa.Text(), nullable=True),
    )
    op.create_index('idx_timeline_events_tenant_date', 'timeline_events', ['tenant_id', 'event_date'])
    op.create_index('idx_timeline_events_type', 'timeline_events', ['tenant_id', 'event_type'])


def downgrade() -> None:
    op.drop_index('idx_timeline_events_type')
    op.drop_index('idx_timeline_events_tenant_date')
    op.drop_table('timeline_events')
