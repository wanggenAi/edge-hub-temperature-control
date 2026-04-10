"""add ops runbooks table for editable markdown content

Revision ID: 20260410_0005
Revises: 20260408_0004
Create Date: 2026-04-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0005"
down_revision = "20260408_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_runbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("section", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("markdown_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_customized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_ops_runbooks_key"),
    )
    op.create_index("ix_ops_runbooks_id", "ops_runbooks", ["id"], unique=False)
    op.create_index("ix_ops_runbooks_key", "ops_runbooks", ["key"], unique=True)
    op.create_index("ix_ops_runbooks_section", "ops_runbooks", ["section"], unique=False)
    op.create_index("ix_ops_runbooks_is_active", "ops_runbooks", ["is_active"], unique=False)
    op.create_index("ix_ops_runbooks_is_customized", "ops_runbooks", ["is_customized"], unique=False)
    op.create_index("ix_ops_runbooks_created_at", "ops_runbooks", ["created_at"], unique=False)
    op.create_index("ix_ops_runbooks_updated_at", "ops_runbooks", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ops_runbooks_updated_at", table_name="ops_runbooks")
    op.drop_index("ix_ops_runbooks_created_at", table_name="ops_runbooks")
    op.drop_index("ix_ops_runbooks_is_customized", table_name="ops_runbooks")
    op.drop_index("ix_ops_runbooks_is_active", table_name="ops_runbooks")
    op.drop_index("ix_ops_runbooks_section", table_name="ops_runbooks")
    op.drop_index("ix_ops_runbooks_key", table_name="ops_runbooks")
    op.drop_index("ix_ops_runbooks_id", table_name="ops_runbooks")
    op.drop_table("ops_runbooks")
