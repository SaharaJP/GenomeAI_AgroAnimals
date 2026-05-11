"""postgres: tasks_v1.source_insight_id for back-ref to scanner_insights

Revision ID: 20260512_16_tasks_v1_source_insight_id
Revises: 20260512_15_briefing_schedule
"""
from alembic import op
import sqlalchemy as sa

revision = '20260512_16_tasks_v1_source_insight_id'
down_revision = '20260512_15_briefing_schedule'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE tasks_v1 ADD COLUMN IF NOT EXISTS source_insight_id TEXT"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_v1_source_insight "
        "ON tasks_v1 (tenant_id, source_insight_id) WHERE source_insight_id IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_tasks_v1_source_insight"))
    op.execute(sa.text("ALTER TABLE tasks_v1 DROP COLUMN IF EXISTS source_insight_id"))
