\
"""postgres table weekly_briefs for AI weekly briefings (MVP-N17)

Revision ID: 20260423_06_weekly_briefs
Revises: 20260422_05_morning_briefs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260423_06_weekly_briefs'
down_revision = '20260422_05_morning_briefs'
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        'weekly_briefs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('brief_id', sa.Text(), nullable=False, unique=True),
        sa.Column('farm_id', sa.Text(), nullable=False),
        sa.Column('week_start', sa.Text(), nullable=False),
        sa.Column('week_end', sa.Text(), nullable=False),
        sa.Column('week_date', sa.Text(), nullable=False),
        sa.Column('generated_at_utc', sa.Text(), nullable=False),
        sa.Column('executive_summary', sa.Text(), nullable=False),
        sa.Column('payload_json', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('generation_model', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False, server_default=sa.text("to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')")),
    )
    op.create_index('idx_weekly_briefs_farm_date', 'weekly_briefs', ['farm_id', sa.text('week_date DESC')])
    op.create_index('idx_weekly_briefs_brief_id', 'weekly_briefs', ['brief_id'])


def downgrade() -> None:
    op.drop_index('idx_weekly_briefs_brief_id', table_name='weekly_briefs')
    op.drop_index('idx_weekly_briefs_farm_date', table_name='weekly_briefs')
    op.drop_table('weekly_briefs')
