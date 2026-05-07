"""postgres: extend scanner_insights and add insight_settings + insight_scan_state

Revision ID: 20260507_12_insights_extend
Revises: 20260504_11_analytics_indexes
"""

from alembic import op
import sqlalchemy as sa

revision = '20260507_12_insights_extend'
down_revision = '20260504_11_analytics_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend scanner_insights
    op.execute(sa.text("""
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS severity TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS body TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS animal_ids JSONB;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS recommendations JSONB;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS chart_data JSONB;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS edited_by TEXT;
ALTER TABLE scanner_insights ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
"""))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS scanner_insights_farm_status_idx "
        "ON scanner_insights (farm_id, status) WHERE deleted_at IS NULL"
    ))

    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS insight_settings (
  user_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  min_severity TEXT NOT NULL DEFAULT 'info',
  enabled_categories JSONB NOT NULL DEFAULT '["production","reproduction","health","feeding","welfare","economics"]',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, farm_id)
)
"""))

    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS insight_scan_state (
  farm_id TEXT PRIMARY KEY,
  last_scan_at TIMESTAMPTZ,
  last_skipped_reason TEXT
)
"""))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS insight_scan_state"))
    op.execute(sa.text("DROP TABLE IF EXISTS insight_settings"))
    op.execute(sa.text("DROP INDEX IF EXISTS scanner_insights_farm_status_idx"))
    for col in ("severity", "body", "action", "animal_ids", "recommendations",
                "chart_data", "edited_at", "edited_by", "deleted_at"):
        op.execute(sa.text(f"ALTER TABLE scanner_insights DROP COLUMN IF EXISTS {col}"))
