"""postgres: add approval_requested_at to weekly_plans_v1

Revision ID: 20260425_08_weekly_plans_approval_requested_at
Revises: 20260425_07_playbooks_weekly_plans_postgres
"""

revision = '20260425_08_weekly_plans_approval_requested_at'
down_revision = '20260425_07_playbooks_weekly_plans_postgres'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        'weekly_plans_v1',
        sa.Column('approval_requested_at', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('weekly_plans_v1', 'approval_requested_at')
