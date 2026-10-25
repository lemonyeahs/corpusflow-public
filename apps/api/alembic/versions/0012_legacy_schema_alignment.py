"""Align historical P1-A/C PostgreSQL columns with the already established model.

Earlier bootstrap migrations created current model tables on new databases,
masking differences on incrementally upgraded databases. No business values or
published files are changed; missing timestamps cause an explicit block.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_legacy_schema_alignment"
down_revision = "0011_p1d_rag"
branch_labels = None
depends_on = None

JSON_COLUMNS = {
    "dataset_quality_reports": ["report_json"],
    "dataset_version_comparisons": ["comparison_json"],
    "node_runs": ["config_snapshot"],
    "operator_definitions": ["input_schema", "output_schema", "params_schema"],
    "quality_evaluation_runs": ["config_snapshot"],
    "quality_metric_results": ["threshold_json", "scope_json", "evidence_json"],
    "quality_rule_versions": ["rules_json"],
    "segments": ["location_json"],
}
TIMESTAMP_TABLES = [
    "dataset_quality_reports",
    "dataset_version_comparisons",
    "operator_definitions",
    "quality_evaluation_runs",
    "quality_metric_results",
    "quality_rule_sets",
    "quality_rule_versions",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    # Preflight the entire change before altering anything. Never invent history.
    for table in TIMESTAMP_TABLES:
        missing = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE created_at IS NULL OR updated_at IS NULL")
        ).scalar_one()
        if missing:
            raise RuntimeError(f"LEGACY_TIMESTAMP_MISSING: {table}; migration rolled back")
    for table, names in JSON_COLUMNS.items():
        columns = {c["name"]: c for c in inspector.get_columns(table)}
        for name in names:
            if not isinstance(columns[name]["type"], JSONB):
                op.alter_column(table, name, type_=JSONB(), postgresql_using=f"{name}::jsonb")
    for table in TIMESTAMP_TABLES:
        for name in ("created_at", "updated_at"):
            op.alter_column(table, name, nullable=False)
    if "ix_document_versions_run_id" not in {
        i["name"] for i in inspector.get_indexes("document_versions")
    }:
        op.create_index("ix_document_versions_run_id", "document_versions", ["run_id"])


def downgrade() -> None:
    # Forward normalization: preserve canonical JSON values, non-null constraints
    # and the harmless index even when rolling application code back to 0011.
    # Reintroducing historical schema drift would not restore original bytes.
    pass
