"""expand ai_recommendations text fields

Revision ID: 20260407_0003
Revises: 20260405_0002
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0003"
down_revision = "20260405_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_recommendations",
        "reason",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "ai_recommendations",
        "suggestion",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "ai_recommendations",
        "risk",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
        existing_nullable=False,
        existing_server_default="Minor overshoot risk",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_recommendations",
        "risk",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
        existing_nullable=False,
        existing_server_default="Minor overshoot risk",
    )
    op.alter_column(
        "ai_recommendations",
        "suggestion",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "ai_recommendations",
        "reason",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
