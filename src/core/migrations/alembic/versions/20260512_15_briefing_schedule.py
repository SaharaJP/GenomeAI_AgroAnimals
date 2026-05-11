"""postgres: briefing_schedule_v1 (per-tenant briefing periodicity / time / auto-task flag)

Revision ID: 20260512_15_briefing_schedule
Revises: 20260509_14_ai_call_log
"""
from alembic import op
import sqlalchemy as sa

revision = '20260512_15_briefing_schedule'
down_revision = '20260509_14_ai_call_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS briefing_schedule_v1 (
  tenant_id          TEXT PRIMARY KEY,
  periodicity        TEXT NOT NULL DEFAULT 'weekly',
  time_of_day        TEXT NOT NULL DEFAULT '07:00',
  auto_create_tasks  BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by         INTEGER
)
"""))
    op.execute(sa.text(
        "ALTER TABLE briefing_schedule_v1 ADD CONSTRAINT briefing_schedule_periodicity_chk "
        "CHECK (periodicity IN ('daily','weekly','monthly'))"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS briefing_schedule_v1"))
