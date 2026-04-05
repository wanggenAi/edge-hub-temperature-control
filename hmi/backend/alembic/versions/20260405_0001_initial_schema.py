"""initial relational schema

Revision ID: 20260405_0001
Revises: 
Create Date: 2026-04-05 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260405_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
    )
    op.create_index("ix_roles_id", "roles", ["id"], unique=False)
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("line", sa.String(length=64), nullable=False, server_default="Line 1"),
        sa.Column("location", sa.String(length=128), nullable=False, server_default="Factory"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("current_temp", sa.Float(), nullable=False, server_default="25.0"),
        sa.Column("target_temp", sa.Float(), nullable=False, server_default="37.0"),
        sa.Column("pwm_output", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_alarm", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_devices_id", "devices", ["id"], unique=False)
    op.create_index("ix_devices_code", "devices", ["code"], unique=True)

    op.create_table(
        "alarm_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("operator", sa.String(length=16), nullable=False, server_default=">"),
        sa.Column("threshold", sa.String(length=128), nullable=False),
        sa.Column("hold_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scope_type", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("scope_value", sa.String(length=128), nullable=False, server_default="*"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False, server_default="system"),
    )
    op.create_index("ix_alarm_rules_id", "alarm_rules", ["id"], unique=False)
    op.create_index("ix_alarm_rules_rule_code", "alarm_rules", ["rule_code"], unique=True)

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_id", "user_roles", ["id"], unique=False)
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False)
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False)

    op.create_table(
        "user_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "device_id", name="uq_user_device"),
    )
    op.create_index("ix_user_devices_id", "user_devices", ["id"], unique=False)
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"], unique=False)
    op.create_index("ix_user_devices_device_id", "user_devices", ["device_id"], unique=False)

    op.create_table(
        "device_parameters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kp", sa.Float(), nullable=False, server_default="2.8"),
        sa.Column("ki", sa.Float(), nullable=False, server_default="0.45"),
        sa.Column("kd", sa.Float(), nullable=False, server_default="0.12"),
        sa.Column("control_mode", sa.String(length=32), nullable=False, server_default="pid_control"),
        sa.Column("target_band", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("overshoot_limit_pct", sa.Float(), nullable=False, server_default="3.0"),
        sa.Column("saturation_warn_ratio", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("saturation_high_ratio", sa.Float(), nullable=False, server_default="0.6"),
        sa.Column("pwm_saturation_threshold", sa.Float(), nullable=False, server_default="85.0"),
        sa.Column("steady_window_samples", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("sampling_period_ms", sa.Integer(), nullable=False, server_default="250"),
        sa.Column("upload_period_s", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False, server_default="system"),
    )
    op.create_index("ix_device_parameters_id", "device_parameters", ["id"], unique=False)
    op.create_index("ix_device_parameters_device_id", "device_parameters", ["device_id"], unique=False)

    op.create_table(
        "device_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("current_temp", sa.Float(), nullable=False),
        sa.Column("target_temp", sa.Float(), nullable=False),
        sa.Column("error", sa.Float(), nullable=False),
        sa.Column("pwm_output", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("in_spec", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_alarm", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_device_metrics_id", "device_metrics", ["id"], unique=False)
    op.create_index("ix_device_metrics_device_id", "device_metrics", ["device_id"], unique=False)
    op.create_index("ix_device_metrics_timestamp", "device_metrics", ["timestamp"], unique=False)

    op.create_table(
        "device_alarms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("rule_code", sa.String(length=64), nullable=False, server_default="out_of_band"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="rule_engine"),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("cleared_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_device_alarms_id", "device_alarms", ["id"], unique=False)
    op.create_index("ix_device_alarms_device_id", "device_alarms", ["device_id"], unique=False)
    op.create_index("ix_device_alarms_rule_code", "device_alarms", ["rule_code"], unique=False)
    op.create_index("ix_device_alarms_source", "device_alarms", ["source"], unique=False)

    op.create_table(
        "ai_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("suggestion", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.78"),
        sa.Column("risk", sa.String(length=128), nullable=False, server_default="Minor overshoot risk"),
        sa.Column("last_run_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_recommendations_id", "ai_recommendations", ["id"], unique=False)
    op.create_index("ix_ai_recommendations_device_id", "ai_recommendations", ["device_id"], unique=False)

    op.create_table(
        "device_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_temp", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("avg_error", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_overshoot_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("saturation_ratio", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("trigger_event", sa.String(length=64), nullable=False, server_default="steady_state_window"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_device_summaries_id", "device_summaries", ["id"], unique=False)
    op.create_index("ix_device_summaries_device_id", "device_summaries", ["device_id"], unique=False)
    op.create_index("ix_device_summaries_window_start", "device_summaries", ["window_start"], unique=False)
    op.create_index("ix_device_summaries_window_end", "device_summaries", ["window_end"], unique=False)
    op.create_index("ix_device_summaries_created_at", "device_summaries", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_device_summaries_created_at", table_name="device_summaries")
    op.drop_index("ix_device_summaries_window_end", table_name="device_summaries")
    op.drop_index("ix_device_summaries_window_start", table_name="device_summaries")
    op.drop_index("ix_device_summaries_device_id", table_name="device_summaries")
    op.drop_index("ix_device_summaries_id", table_name="device_summaries")
    op.drop_table("device_summaries")

    op.drop_index("ix_ai_recommendations_device_id", table_name="ai_recommendations")
    op.drop_index("ix_ai_recommendations_id", table_name="ai_recommendations")
    op.drop_table("ai_recommendations")

    op.drop_index("ix_device_alarms_source", table_name="device_alarms")
    op.drop_index("ix_device_alarms_rule_code", table_name="device_alarms")
    op.drop_index("ix_device_alarms_device_id", table_name="device_alarms")
    op.drop_index("ix_device_alarms_id", table_name="device_alarms")
    op.drop_table("device_alarms")

    op.drop_index("ix_device_metrics_timestamp", table_name="device_metrics")
    op.drop_index("ix_device_metrics_device_id", table_name="device_metrics")
    op.drop_index("ix_device_metrics_id", table_name="device_metrics")
    op.drop_table("device_metrics")

    op.drop_index("ix_device_parameters_device_id", table_name="device_parameters")
    op.drop_index("ix_device_parameters_id", table_name="device_parameters")
    op.drop_table("device_parameters")

    op.drop_index("ix_user_devices_device_id", table_name="user_devices")
    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_index("ix_user_devices_id", table_name="user_devices")
    op.drop_table("user_devices")

    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_index("ix_user_roles_id", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("ix_alarm_rules_rule_code", table_name="alarm_rules")
    op.drop_index("ix_alarm_rules_id", table_name="alarm_rules")
    op.drop_table("alarm_rules")

    op.drop_index("ix_devices_code", table_name="devices")
    op.drop_index("ix_devices_id", table_name="devices")
    op.drop_table("devices")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_index("ix_roles_id", table_name="roles")
    op.drop_table("roles")
