"""postgres: personnel_v1.user_id soft-FK to runtime auth users (P1-4b-3a)

Revision ID: 20260515_18_personnel_user_id
Revises: 20260515_17_personnel_v1

Adds a nullable INTEGER user_id column to personnel_v1 so that a personnel
record can be linked to an authenticated user. The link is "soft" — no DB-
level FK constraint, because runtime auth users live in a separate logical
storage and the personnel record may pre-exist (HR-side) before the user
account is provisioned.

Used by P1-4b-3b to fetch personal tasks via /worklists?owner_user_id=.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260515_18_personnel_user_id'
down_revision = '20260515_17_personnel_v1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE personnel_v1 ADD COLUMN IF NOT EXISTS user_id INTEGER"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_personnel_v1_tenant_user "
        "ON personnel_v1 (tenant_id, user_id) WHERE user_id IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_personnel_v1_tenant_user"))
    op.execute(sa.text("ALTER TABLE personnel_v1 DROP COLUMN IF EXISTS user_id"))
