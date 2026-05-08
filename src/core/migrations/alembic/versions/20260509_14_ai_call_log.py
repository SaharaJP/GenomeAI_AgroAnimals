"""postgres: ai_call_log table for AI observability admin panel

Revision ID: 20260509_14_ai_call_log
Revises: 20260507_13_qc_incidents
"""
from alembic import op
import sqlalchemy as sa

revision = '20260509_14_ai_call_log'
down_revision = '20260507_13_qc_incidents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
CREATE TABLE IF NOT EXISTS ai_call_log (
  id                    BIGSERIAL PRIMARY KEY,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  user_id               VARCHAR(64),
  endpoint              VARCHAR(64) NOT NULL,
  task_type             VARCHAR(32) NOT NULL,
  model                 VARCHAR(64) NOT NULL,
  input_tokens          INTEGER NOT NULL DEFAULT 0,
  output_tokens         INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
  cost_usd              NUMERIC(10, 6) NOT NULL DEFAULT 0,
  latency_ms            INTEGER NOT NULL DEFAULT 0,
  error                 TEXT,
  prompt                TEXT,
  response              TEXT,
  evidence_chips        JSONB,
  tools_used            JSONB
)
"""))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_ai_call_log_created_at "
        "ON ai_call_log (created_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_ai_call_log_endpoint "
        "ON ai_call_log (endpoint)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_ai_call_log_user_id "
        "ON ai_call_log (user_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_call_log_user_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_call_log_endpoint"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_call_log_created_at"))
    op.execute(sa.text("DROP TABLE IF EXISTS ai_call_log"))
