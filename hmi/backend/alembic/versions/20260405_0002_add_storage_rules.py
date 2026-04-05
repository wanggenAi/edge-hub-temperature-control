"""add storage rules

Revision ID: 20260405_0002
Revises: 20260405_0001
Create Date: 2026-04-05 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260405_0002"
down_revision = "20260405_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("scope_value", sa.String(length=128), nullable=False, server_default="*"),
        sa.Column("raw_mode", sa.String(length=16), nullable=False, server_default="full"),
        sa.Column("summary_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("summary_min_samples", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("heartbeat_interval_ms", sa.Integer(), nullable=False, server_default="30000"),
        sa.Column("target_temp_deadband", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("sim_temp_deadband", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("sensor_temp_deadband", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("error_deadband", sa.Float(), nullable=False, server_default="0.02"),
        sa.Column("integral_error_deadband", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("control_output_deadband", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pwm_duty_deadband", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pwm_norm_deadband", sa.Float(), nullable=False, server_default="0.01"),
        sa.Column("parameter_deadband", sa.Float(), nullable=False, server_default="0.01"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False, server_default="system"),
        sa.UniqueConstraint("scope_type", "scope_value", name="uq_storage_rule_scope"),
    )
    op.create_index("ix_storage_rules_id", "storage_rules", ["id"], unique=False)
    op.create_index("ix_storage_rules_scope_type", "storage_rules", ["scope_type"], unique=False)
    op.create_index("ix_storage_rules_scope_value", "storage_rules", ["scope_value"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_storage_rules_scope_value", table_name="storage_rules")
    op.drop_index("ix_storage_rules_scope_type", table_name="storage_rules")
    op.drop_index("ix_storage_rules_id", table_name="storage_rules")
    op.drop_table("storage_rules")
