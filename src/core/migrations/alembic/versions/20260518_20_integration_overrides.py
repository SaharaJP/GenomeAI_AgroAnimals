"""postgres: integration_overrides_v1 — admin enable/disable for integrations (P1-6b)

Revision ID: 20260518_20_integration_overrides
Revises: 20260515_19_role_permissions_overrides

Stores per-tenant admin override on the enabled state of an integration provider.
Absence of row = enabled (the integration's natural state). When `enabled = FALSE`
the /integrations/health aggregator forces status='disabled' for that row and
exposes a note explaining the admin override.

Schema:
  - integration_id: TEXT — provider id as exposed in IntegrationHealth.id
  - tenant_id: TEXT — caller tenant
  - enabled: BOOLEAN — current admin choice
  - updated_at: TIMESTAMPTZ
  - updated_by_user_id: INTEGER — soft-FK to auth user
  - updated_by_username: TEXT
  - PRIMARY KEY (integration_id, tenant_id) — one override per pair
"""
from alembic import op
import sqlalchemy as sa

revision = '20260518_20_integration_overrides'
down_revision = '20260515_19_role_permissions_overrides'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS integration_overrides_v1 (
            integration_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            enabled BOOLEAN NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_user_id INTEGER,
            updated_by_username TEXT,
            PRIMARY KEY (integration_id, tenant_id)
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_integration_overrides_tenant "
        "ON integration_overrides_v1 (tenant_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_integration_overrides_tenant"))
    op.execute(sa.text("DROP TABLE IF EXISTS integration_overrides_v1"))
