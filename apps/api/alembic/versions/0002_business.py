"""P0-B through P0-F domain tables.

The operation is idempotent so local databases created with the original
P0-A placeholder revision can be upgraded without a destructive reset.
"""

from alembic import op
from corpusflow.db import models  # noqa: F401
from corpusflow.db.session import Base

revision = "0002_business"
down_revision = "0001_p0a"
branch_labels = None
depends_on = None


# Freeze legacy bootstrap table scope; future tables belong to later migrations.
TABLES = [
    "asset_blobs",
    "audit_events",
    "dataset_definitions",
    "discovery_candidates",
    "ingest_batches",
    "lineage_edges",
    "operator_definitions",
    "outbox_events",
    "pipeline_templates",
    "processing_batches",
    "quality_issues",
    "quality_rule_sets",
    "upload_sessions",
    "users",
    "workspaces",
    "dataset_builds",
    "ingest_batch_items",
    "pipeline_versions",
    "quality_reviews",
    "quality_rule_versions",
    "sources",
    "workspace_memberships",
    "assets",
    "candidate_samples",
    "dataset_versions",
    "license_evidence",
    "quality_evaluation_runs",
    "dataset_quality_reports",
    "dataset_version_artifacts",
    "dataset_version_comparisons",
    "dataset_version_samples",
    "documents",
    "license_grants",
    "pipeline_runs",
    "quality_metric_results",
    "sample_reviews",
    "artifacts",
    "document_versions",
    "execution_logs",
    "node_runs",
    "segments",
    "dataset_build_inputs",
    "sample_evidence",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[n] for n in TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[n] for n in TABLES])
