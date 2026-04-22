"""insights table — MVP-N03

Revision ID: 20260422_05_insights_table_postgres
Revises: 20260418_04_runtime_feedback_completion_postgres
Create Date: 2026-04-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260422_05_insights_table_postgres'
down_revision = '20260418_04_runtime_feedback_completion_postgres'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'insights',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('insight_id', sa.Text(), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('farm_id', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('severity', sa.Text(), nullable=False, server_default=sa.text("'info'")),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'to_check'")),
        sa.Column('date', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('action', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('animal_ids', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('tags', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('chart_data', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('chart_label', sa.Text(), nullable=True),
        sa.Column('chart_unit', sa.Text(), nullable=True),
        sa.Column('farm_pct', sa.Float(), nullable=True),
        sa.Column('holding_pct', sa.Float(), nullable=True),
        sa.Column('recommendations', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
    )
    op.create_index(
        'idx_insights_tenant_status',
        'insights',
        ['tenant_id', 'status', sa.text('created_at DESC')],
    )
    op.create_index(
        'idx_insights_tenant_farm',
        'insights',
        ['tenant_id', 'farm_id'],
    )
    op.create_index(
        'idx_insights_insight_id',
        'insights',
        ['insight_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('idx_insights_insight_id', table_name='insights')
    op.drop_index('idx_insights_tenant_farm', table_name='insights')
    op.drop_index('idx_insights_tenant_status', table_name='insights')
    op.drop_table('insights')
