"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations


def upgrade() -> None:
    raise NotImplementedError("T34 staged Postgres runtime migrations are not implemented yet")


def downgrade() -> None:
    raise NotImplementedError("T34 staged Postgres runtime migrations are not implemented yet")
