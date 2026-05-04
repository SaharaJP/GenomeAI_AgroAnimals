"""analytics: performance indexes on dm_milkings_daily, dm_health_events, dm_repro_events, dm_sensors_daily

Revision ID: 20260504_11_analytics_indexes
Revises: 20260503_10_domain_model_tables
"""

from alembic import op
import sqlalchemy as sa

revision = '20260504_11_analytics_indexes'
down_revision = '20260503_10_domain_model_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_milkings_tenant_date "
        "ON dm_milkings_daily (tenant_id, date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_milkings_animal_date "
        "ON dm_milkings_daily (animal_id, date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_health_tenant_date "
        "ON dm_health_events (tenant_id, event_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_health_animal_date "
        "ON dm_health_events (animal_id, event_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_repro_tenant_date "
        "ON dm_repro_events (tenant_id, event_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_sensors_animal_date "
        "ON dm_sensors_daily (animal_id, date)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_sensors_animal_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_repro_tenant_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_health_animal_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_health_tenant_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_milkings_animal_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_milkings_tenant_date"))
