"""postgres: qc_incidents + qc_scan_state + timeline_events.linked_metric_ids

Revision ID: 20260507_13_qc_incidents
Revises: 20260507_12_insights_extend
"""
from alembic import op
import sqlalchemy as sa

revision = '20260507_13_qc_incidents'
down_revision = '20260507_12_insights_extend'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS qc_incidents (
  incident_id      TEXT PRIMARY KEY,
  farm_id          TEXT NOT NULL,
  metric_id        TEXT NOT NULL,
  period_start     TIMESTAMPTZ NOT NULL,
  period_end       TIMESTAMPTZ,
  detector_type    TEXT NOT NULL,
  severity         TEXT NOT NULL DEFAULT 'warn',
  affected_sensors JSONB NOT NULL DEFAULT '[]',
  ai_description   TEXT,
  root_cause       TEXT,
  status           TEXT NOT NULL DEFAULT 'active',
  detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at      TIMESTAMPTZ
)
"""))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS qc_incidents_farm_metric_idx "
        "ON qc_incidents (farm_id, metric_id, period_start) WHERE status = 'active'"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS qc_incidents_dedup_idx "
        "ON qc_incidents (farm_id, metric_id, detector_type, period_start)"
    ))
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS qc_scan_state (
  farm_id             TEXT PRIMARY KEY,
  last_scan_at        TIMESTAMPTZ,
  last_skipped_reason TEXT
)
"""))
    op.execute(sa.text(
        "ALTER TABLE timeline_events "
        "ADD COLUMN IF NOT EXISTS linked_metric_ids JSONB NOT NULL DEFAULT '[]'"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE timeline_events DROP COLUMN IF EXISTS linked_metric_ids"))
    op.execute(sa.text("DROP TABLE IF EXISTS qc_scan_state"))
    op.execute(sa.text("DROP INDEX IF EXISTS qc_incidents_dedup_idx"))
    op.execute(sa.text("DROP INDEX IF EXISTS qc_incidents_farm_metric_idx"))
    op.execute(sa.text("DROP TABLE IF EXISTS qc_incidents"))
