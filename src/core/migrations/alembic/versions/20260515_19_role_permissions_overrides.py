"""postgres: role_permissions_overrides_v1 — DB overrides over YAML matrix (P1-5)

Revision ID: 20260515_19_role_permissions_overrides
Revises: 20260515_18_personnel_user_id

Adds a table for runtime DB-overrides on top of the YAML permission matrix
(configs/security/permission_matrix_v1.yaml). Effective permissions for a
role = YAML.union(grants) minus revokes.

Schema:
  - role: TEXT — role name from policy constants
  - permission: TEXT — permission code (must exist in ALL_PERMISSIONS)
  - effect: TEXT 'grant' | 'revoke'
  - created_at: TIMESTAMPTZ
  - created_by_user_id: INTEGER — soft-FK to auth user
  - created_by_username: TEXT
  - PRIMARY KEY (role, permission) — at most one effect per pair
"""
from alembic import op
import sqlalchemy as sa

revision = '20260515_19_role_permissions_overrides'
down_revision = '20260515_18_personnel_user_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS role_permissions_overrides_v1 (
            role TEXT NOT NULL,
            permission TEXT NOT NULL,
            effect TEXT NOT NULL CHECK (effect IN ('grant', 'revoke')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by_user_id INTEGER,
            created_by_username TEXT,
            PRIMARY KEY (role, permission)
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_role_perm_overrides_role "
        "ON role_permissions_overrides_v1 (role)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_role_perm_overrides_role"))
    op.execute(sa.text("DROP TABLE IF EXISTS role_permissions_overrides_v1"))
