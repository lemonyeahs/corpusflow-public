"""Initial CorpusFlow schema.

The first shipped migration contains the P0 business loop so a disposable
database can be upgraded and downgraded as one coherent unit.
"""

from alembic import op
from corpusflow.db.models import (  # noqa: F401
    Asset,
    AssetBlob,
    AuditEvent,
    BuildInput,
    CandidateSample,
    Dataset,
    DatasetBuild,
    DatasetVersion,
    DatasetVersionSample,
    DiscoveryCandidate,
    Document,
    DocumentVersion,
    IngestBatch,
    IngestItem,
    LicenseEvidence,
    LicenseGrant,
    LineageEdge,
    Membership,
    NodeRun,
    PipelineRun,
    PipelineTemplate,
    PipelineVersion,
    ProcessingBatch,
    QualityIssue,
    QualityReview,
    SampleEvidence,
    SampleReview,
    Segment,
    Source,
    UploadSession,
    User,
    Workspace,
)
from corpusflow.db.session import Base

revision = "0001_p0a"
down_revision = None
branch_labels = None
depends_on = None


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
