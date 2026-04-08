"""add unified control-action learning loop tables

Revision ID: 20260408_0004
Revises: 20260407_0003
Create Date: 2026-04-08 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0004"
down_revision = "20260407_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual_user"),
        sa.Column("source_ref_id", sa.Integer(), sa.ForeignKey("ai_recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False, server_default="pid_apply"),
        sa.Column("initiated_by", sa.String(length=128), nullable=False, server_default="system"),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="applied"),
        sa.Column("control_mode_before", sa.String(length=32), nullable=True),
        sa.Column("control_mode_after", sa.String(length=32), nullable=True),
        sa.Column("target_temp_before", sa.Float(), nullable=True),
        sa.Column("target_temp_after", sa.Float(), nullable=True),
        sa.Column("kp_before", sa.Float(), nullable=True),
        sa.Column("ki_before", sa.Float(), nullable=True),
        sa.Column("kd_before", sa.Float(), nullable=True),
        sa.Column("kp_after", sa.Float(), nullable=True),
        sa.Column("ki_after", sa.Float(), nullable=True),
        sa.Column("kd_after", sa.Float(), nullable=True),
        sa.Column("delta_kp", sa.Float(), nullable=True),
        sa.Column("delta_ki", sa.Float(), nullable=True),
        sa.Column("delta_kd", sa.Float(), nullable=True),
        sa.Column("context_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_control_actions_id", "control_actions", ["id"], unique=False)
    op.create_index("ix_control_actions_device_id", "control_actions", ["device_id"], unique=False)
    op.create_index("ix_control_actions_source", "control_actions", ["source"], unique=False)
    op.create_index("ix_control_actions_source_ref_id", "control_actions", ["source_ref_id"], unique=False)
    op.create_index("ix_control_actions_action_type", "control_actions", ["action_type"], unique=False)
    op.create_index("ix_control_actions_applied_at", "control_actions", ["applied_at"], unique=False)
    op.create_index("ix_control_actions_status", "control_actions", ["status"], unique=False)
    op.create_index("ix_control_actions_created_at", "control_actions", ["created_at"], unique=False)

    op.create_table(
        "control_action_eval_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_action_id", sa.Integer(), sa.ForeignKey("control_actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("observation_window_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_control_action_eval_jobs_id", "control_action_eval_jobs", ["id"], unique=False)
    op.create_index("ix_control_action_eval_jobs_control_action_id", "control_action_eval_jobs", ["control_action_id"], unique=False)
    op.create_index("ix_control_action_eval_jobs_device_id", "control_action_eval_jobs", ["device_id"], unique=False)
    op.create_index("ix_control_action_eval_jobs_status", "control_action_eval_jobs", ["status"], unique=False)
    op.create_index("ix_control_action_eval_jobs_scheduled_at", "control_action_eval_jobs", ["scheduled_at"], unique=False)
    op.create_index("ix_control_action_eval_jobs_created_at", "control_action_eval_jobs", ["created_at"], unique=False)

    op.create_table(
        "control_action_feedback_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_action_id", sa.Integer(), sa.ForeignKey("control_actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual_user"),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False, server_default="pid_apply"),
        sa.Column("initiated_by", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("primary_problem_type", sa.String(length=64), nullable=True),
        sa.Column("secondary_problem_types", sa.JSON(), nullable=True),
        sa.Column("problem_flags", sa.JSON(), nullable=True),
        sa.Column("expected_effect", sa.String(length=64), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("control_mode_before", sa.String(length=32), nullable=True),
        sa.Column("control_mode_after", sa.String(length=32), nullable=True),
        sa.Column("target_temp_before", sa.Float(), nullable=True),
        sa.Column("target_temp_after", sa.Float(), nullable=True),
        sa.Column("kp_before", sa.Float(), nullable=True),
        sa.Column("ki_before", sa.Float(), nullable=True),
        sa.Column("kd_before", sa.Float(), nullable=True),
        sa.Column("kp_after", sa.Float(), nullable=True),
        sa.Column("ki_after", sa.Float(), nullable=True),
        sa.Column("kd_after", sa.Float(), nullable=True),
        sa.Column("delta_kp", sa.Float(), nullable=True),
        sa.Column("delta_ki", sa.Float(), nullable=True),
        sa.Column("delta_kd", sa.Float(), nullable=True),
        sa.Column("mean_error", sa.Float(), nullable=True),
        sa.Column("mean_abs_error", sa.Float(), nullable=True),
        sa.Column("error_std", sa.Float(), nullable=True),
        sa.Column("temp_swing", sa.Float(), nullable=True),
        sa.Column("pwm_mean", sa.Float(), nullable=True),
        sa.Column("pwm_max", sa.Float(), nullable=True),
        sa.Column("zero_crossings", sa.Integer(), nullable=True),
        sa.Column("in_band_ratio", sa.Float(), nullable=True),
        sa.Column("overshoot_pct", sa.Float(), nullable=True),
        sa.Column("settling_sec", sa.Float(), nullable=True),
        sa.Column("saturation_ratio", sa.Float(), nullable=True),
        sa.Column("runtime_decision_summary", sa.JSON(), nullable=True),
        sa.Column("preview_metrics_summary", sa.JSON(), nullable=True),
        sa.Column("actual_metrics_summary", sa.JSON(), nullable=True),
        sa.Column("comparison_to_before", sa.JSON(), nullable=True),
        sa.Column("comparison_to_preview", sa.JSON(), nullable=True),
        sa.Column("actual_effect_label", sa.String(length=32), nullable=True),
        sa.Column("preview_gap_label", sa.String(length=32), nullable=True),
        sa.Column("insufficient_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sample_quality", sa.String(length=32), nullable=False, server_default="reject"),
        sa.Column("is_training_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("training_exclusion_reason", sa.Text(), nullable=True),
        sa.Column("label_source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("control_action_id", name="uq_control_action_feedback_control_action_id"),
    )
    op.create_index("ix_control_action_feedback_samples_id", "control_action_feedback_samples", ["id"], unique=False)
    op.create_index("ix_control_action_feedback_samples_control_action_id", "control_action_feedback_samples", ["control_action_id"], unique=True)
    op.create_index("ix_control_action_feedback_samples_device_id", "control_action_feedback_samples", ["device_id"], unique=False)
    op.create_index("ix_control_action_feedback_samples_source", "control_action_feedback_samples", ["source"], unique=False)
    op.create_index("ix_control_action_feedback_samples_source_ref_id", "control_action_feedback_samples", ["source_ref_id"], unique=False)
    op.create_index("ix_control_action_feedback_samples_applied_at", "control_action_feedback_samples", ["applied_at"], unique=False)
    op.create_index("ix_control_action_feedback_samples_evaluated_at", "control_action_feedback_samples", ["evaluated_at"], unique=False)
    op.create_index("ix_control_action_feedback_samples_primary_problem_type", "control_action_feedback_samples", ["primary_problem_type"], unique=False)
    op.create_index("ix_control_action_feedback_samples_actual_effect_label", "control_action_feedback_samples", ["actual_effect_label"], unique=False)
    op.create_index("ix_control_action_feedback_samples_preview_gap_label", "control_action_feedback_samples", ["preview_gap_label"], unique=False)
    op.create_index("ix_control_action_feedback_samples_insufficient_data", "control_action_feedback_samples", ["insufficient_data"], unique=False)
    op.create_index("ix_control_action_feedback_samples_sample_quality", "control_action_feedback_samples", ["sample_quality"], unique=False)
    op.create_index("ix_control_action_feedback_samples_is_training_eligible", "control_action_feedback_samples", ["is_training_eligible"], unique=False)
    op.create_index("ix_control_action_feedback_samples_created_at", "control_action_feedback_samples", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_control_action_feedback_samples_created_at", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_is_training_eligible", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_sample_quality", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_insufficient_data", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_preview_gap_label", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_actual_effect_label", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_primary_problem_type", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_evaluated_at", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_applied_at", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_source_ref_id", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_source", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_device_id", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_control_action_id", table_name="control_action_feedback_samples")
    op.drop_index("ix_control_action_feedback_samples_id", table_name="control_action_feedback_samples")
    op.drop_table("control_action_feedback_samples")

    op.drop_index("ix_control_action_eval_jobs_created_at", table_name="control_action_eval_jobs")
    op.drop_index("ix_control_action_eval_jobs_scheduled_at", table_name="control_action_eval_jobs")
    op.drop_index("ix_control_action_eval_jobs_status", table_name="control_action_eval_jobs")
    op.drop_index("ix_control_action_eval_jobs_device_id", table_name="control_action_eval_jobs")
    op.drop_index("ix_control_action_eval_jobs_control_action_id", table_name="control_action_eval_jobs")
    op.drop_index("ix_control_action_eval_jobs_id", table_name="control_action_eval_jobs")
    op.drop_table("control_action_eval_jobs")

    op.drop_index("ix_control_actions_created_at", table_name="control_actions")
    op.drop_index("ix_control_actions_status", table_name="control_actions")
    op.drop_index("ix_control_actions_applied_at", table_name="control_actions")
    op.drop_index("ix_control_actions_action_type", table_name="control_actions")
    op.drop_index("ix_control_actions_source_ref_id", table_name="control_actions")
    op.drop_index("ix_control_actions_source", table_name="control_actions")
    op.drop_index("ix_control_actions_device_id", table_name="control_actions")
    op.drop_index("ix_control_actions_id", table_name="control_actions")
    op.drop_table("control_actions")
