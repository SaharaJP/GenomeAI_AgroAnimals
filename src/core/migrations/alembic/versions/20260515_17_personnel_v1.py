"""postgres: personnel_v1 (team members for /team tab — P1-4a)

Revision ID: 20260515_17_personnel_v1
Revises: 20260512_16_tasks_v1_source_insight_id

Schema for the Personnel domain entity introduced in P1-4a. Used by the
/team tab (P1-4b) and by FAB task assignment (P1-4d). PII columns
(phone, email, hired_at) are gated by personnel.read_pii on the API
surface in P1-4a-6 — DB-level encryption is out of scope here.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260515_17_personnel_v1'
down_revision = '20260512_16_tasks_v1_source_insight_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS personnel_v1 (
  personnel_id   TEXT PRIMARY KEY,
  tenant_id      TEXT NOT NULL,
  full_name      TEXT NOT NULL,
  position       TEXT NOT NULL,
  group_id       TEXT,
  photo_ref      TEXT,
  phone          TEXT,
  email          TEXT,
  hired_at       DATE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_personnel_v1_tenant_name "
        "ON personnel_v1 (tenant_id, full_name)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_personnel_v1_tenant_group "
        "ON personnel_v1 (tenant_id, group_id) WHERE group_id IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_personnel_v1_tenant_group"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_personnel_v1_tenant_name"))
    op.execute(sa.text("DROP TABLE IF EXISTS personnel_v1"))
