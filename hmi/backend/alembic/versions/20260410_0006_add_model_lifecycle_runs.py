"""add model lifecycle runs audit table

Revision ID: 20260410_0006
Revises: 20260410_0005
Create Date: 2026-04-10 00:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0006"
down_revision = "20260410_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_lifecycle_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lifecycle_run_id", sa.String(length=64), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("trigger_source", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="skipped"),
        sa.Column("promoted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("gate_reasons", sa.JSON(), nullable=True),
        sa.Column("training_sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_eligible_samples_since_last", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_eligible_samples_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_size", sa.Integer(), nullable=True),
        sa.Column("candidate_artifact_dir", sa.Text(), nullable=True),
        sa.Column("candidate_metrics_path", sa.Text(), nullable=True),
        sa.Column("active_artifact_dir_before", sa.Text(), nullable=True),
        sa.Column("active_metrics_path_before", sa.Text(), nullable=True),
        sa.Column("archive_artifact_dir", sa.Text(), nullable=True),
        sa.Column("candidate_metrics", sa.JSON(), nullable=True),
        sa.Column("active_metrics", sa.JSON(), nullable=True),
        sa.Column("comparison_summary", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_model_lifecycle_runs_id", "model_lifecycle_runs", ["id"], unique=False)
    op.create_index("ix_model_lifecycle_runs_lifecycle_run_id", "model_lifecycle_runs", ["lifecycle_run_id"], unique=False)
    op.create_index("ix_model_lifecycle_runs_model_family", "model_lifecycle_runs", ["model_family"], unique=False)
    op.create_index("ix_model_lifecycle_runs_status", "model_lifecycle_runs", ["status"], unique=False)
    op.create_index("ix_model_lifecycle_runs_promoted", "model_lifecycle_runs", ["promoted"], unique=False)
    op.create_index("ix_model_lifecycle_runs_dry_run", "model_lifecycle_runs", ["dry_run"], unique=False)
    op.create_index("ix_model_lifecycle_runs_started_at", "model_lifecycle_runs", ["started_at"], unique=False)
    op.create_index("ix_model_lifecycle_runs_completed_at", "model_lifecycle_runs", ["completed_at"], unique=False)
    op.create_index("ix_model_lifecycle_runs_created_at", "model_lifecycle_runs", ["created_at"], unique=False)
    op.create_index("ix_model_lifecycle_runs_updated_at", "model_lifecycle_runs", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_model_lifecycle_runs_updated_at", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_created_at", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_completed_at", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_started_at", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_dry_run", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_promoted", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_status", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_model_family", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_lifecycle_run_id", table_name="model_lifecycle_runs")
    op.drop_index("ix_model_lifecycle_runs_id", table_name="model_lifecycle_runs")
    op.drop_table("model_lifecycle_runs")

