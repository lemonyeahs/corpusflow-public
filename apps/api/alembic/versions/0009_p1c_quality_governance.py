"""Versioned quality rules, evaluations, reports and dataset comparisons."""

from alembic import op
import sqlalchemy as sa

revision = "0009_p1c_quality_governance"
down_revision = "0008_p1a_processing"
branch_labels = None
depends_on = None


def _table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table("quality_rule_sets"):
        op.create_table(
            "quality_rule_sets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("product_type", sa.String(30), nullable=False, server_default="*"),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        )
        op.create_index("ix_quality_rule_sets_workspace_id", "quality_rule_sets", ["workspace_id"])
    if not _table("quality_rule_versions"):
        op.create_table(
            "quality_rule_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "rule_set_id", sa.String(36), sa.ForeignKey("quality_rule_sets.id"), nullable=False
            ),
            sa.Column("version", sa.String(50), nullable=False),
            sa.Column("rules_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("config_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
            sa.Column("created_by", sa.String(36), nullable=False),
            sa.UniqueConstraint("rule_set_id", "version", name="uq_quality_rule_version"),
        )
        op.create_index(
            "ix_quality_rule_versions_rule_set_id", "quality_rule_versions", ["rule_set_id"]
        )
    if not _table("quality_evaluation_runs"):
        op.create_table(
            "quality_evaluation_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column(
                "rule_set_id", sa.String(36), sa.ForeignKey("quality_rule_sets.id"), nullable=False
            ),
            sa.Column(
                "rule_version_id",
                sa.String(36),
                sa.ForeignKey("quality_rule_versions.id"),
                nullable=False,
            ),
            sa.Column("target_type", sa.String(40), nullable=False),
            sa.Column("target_id", sa.String(36), nullable=False),
            sa.Column("product_type", sa.String(30), nullable=False, server_default="*"),
            sa.Column("config_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
            sa.Column("metric_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(36), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("error_code", sa.String(80)),
        )
        op.create_index(
            "ix_quality_evaluation_runs_workspace_id", "quality_evaluation_runs", ["workspace_id"]
        )
        op.create_index(
            "ix_quality_evaluation_runs_target_id", "quality_evaluation_runs", ["target_id"]
        )
    if not _table("quality_metric_results"):
        op.create_table(
            "quality_metric_results",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "evaluation_run_id",
                sa.String(36),
                sa.ForeignKey("quality_evaluation_runs.id"),
                nullable=False,
            ),
            sa.Column("metric_id", sa.String(120), nullable=False),
            sa.Column("metric_version", sa.String(40), nullable=False),
            sa.Column("category", sa.String(40), nullable=False),
            sa.Column("value_numeric", sa.Float()),
            sa.Column("numerator", sa.Float()),
            sa.Column("denominator", sa.Float()),
            sa.Column("unit", sa.String(40), nullable=False, server_default="ratio"),
            sa.Column(
                "direction", sa.String(20), nullable=False, server_default="higher_is_better"
            ),
            sa.Column("threshold_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(30), nullable=False, server_default="NOT_EVALUATED"),
            sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="{}"),
        )
        op.create_index(
            "ix_quality_metric_results_evaluation_run_id",
            "quality_metric_results",
            ["evaluation_run_id"],
        )
        op.create_index(
            "ix_quality_metric_results_metric_id", "quality_metric_results", ["metric_id"]
        )
    if not _table("dataset_quality_reports"):
        op.create_table(
            "dataset_quality_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column(
                "dataset_version_id",
                sa.String(36),
                sa.ForeignKey("dataset_versions.id"),
                nullable=False,
            ),
            sa.Column(
                "evaluation_run_id",
                sa.String(36),
                sa.ForeignKey("quality_evaluation_runs.id"),
                nullable=False,
            ),
            sa.Column("report_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("report_sha256", sa.String(64), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="final"),
            sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint(
                "dataset_version_id", "evaluation_run_id", name="uq_dataset_quality_report"
            ),
        )
        op.create_index(
            "ix_dataset_quality_reports_workspace_id", "dataset_quality_reports", ["workspace_id"]
        )
        op.create_index(
            "ix_dataset_quality_reports_dataset_version_id",
            "dataset_quality_reports",
            ["dataset_version_id"],
        )
    if not _table("dataset_version_comparisons"):
        op.create_table(
            "dataset_version_comparisons",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column(
                "left_version_id",
                sa.String(36),
                sa.ForeignKey("dataset_versions.id"),
                nullable=False,
            ),
            sa.Column(
                "right_version_id",
                sa.String(36),
                sa.ForeignKey("dataset_versions.id"),
                nullable=False,
            ),
            sa.Column("comparison_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(30), nullable=False, server_default="completed"),
            sa.Column("created_by", sa.String(36), nullable=False),
            sa.UniqueConstraint(
                "left_version_id", "right_version_id", name="uq_dataset_version_comparison"
            ),
        )
        op.create_index(
            "ix_dataset_version_comparisons_workspace_id",
            "dataset_version_comparisons",
            ["workspace_id"],
        )
        op.create_index(
            "ix_dataset_version_comparisons_left_version_id",
            "dataset_version_comparisons",
            ["left_version_id"],
        )
        op.create_index(
            "ix_dataset_version_comparisons_right_version_id",
            "dataset_version_comparisons",
            ["right_version_id"],
        )


def downgrade() -> None:
    for name in (
        "dataset_version_comparisons",
        "dataset_quality_reports",
        "quality_metric_results",
        "quality_evaluation_runs",
        "quality_rule_versions",
        "quality_rule_sets",
    ):
        if _table(name):
            op.drop_table(name)
