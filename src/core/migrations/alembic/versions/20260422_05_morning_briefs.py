\
"""postgres table morning_briefs for AI daily briefings

Revision ID: 20260422_05_morning_briefs
Revises: 20260418_04_runtime_feedback_completion_postgres
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260422_05_morning_briefs'
down_revision = '20260418_04_runtime_feedback_completion_postgres'
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        'morning_briefs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('brief_id', sa.Text(), nullable=False, unique=True),
        sa.Column('farm_id', sa.Text(), nullable=False),
        sa.Column('brief_date', sa.Text(), nullable=False),
        sa.Column('generated_at_utc', sa.Text(), nullable=False),
        sa.Column('headline', sa.Text(), nullable=False),
        sa.Column('main_takeaway', sa.Text(), nullable=False),
        sa.Column('payload_json', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('generation_model', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False, server_default=sa.text("to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')")),
    )
    op.create_index('idx_morning_briefs_farm_date', 'morning_briefs', ['farm_id', sa.text('brief_date DESC')])
    op.create_index('idx_morning_briefs_brief_id', 'morning_briefs', ['brief_id'])


def downgrade() -> None:
    op.drop_index('idx_morning_briefs_brief_id', table_name='morning_briefs')
    op.drop_index('idx_morning_briefs_farm_date', table_name='morning_briefs')
    op.drop_table('morning_briefs')
