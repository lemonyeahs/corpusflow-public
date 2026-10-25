"""Persistent domain models for the P0 business loop.

The models deliberately use portable SQL types so the policy and state
machines can be exercised in disposable PostgreSQL and SQLite test databases.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON as SAJSON
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from corpusflow.db.session import Base

JSON = SAJSON().with_variant(JSONB, "postgresql")


def uid() -> str:
    return str(uuid4())


class Timestamped(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class User(Timestamped):
    __tablename__ = "users"
    oidc_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Workspace(Timestamped):
    __tablename__ = "workspaces"
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="active")


class Membership(Timestamped):
    __tablename__ = "workspace_memberships"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="active")
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_membership"),)


class AuditEvent(Timestamped):
    __tablename__ = "audit_events"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Source(Timestamped):
    __tablename__ = "sources"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(50), default="upload")
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LicenseEvidence(Timestamped):
    __tablename__ = "license_evidence"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    uri: Mapped[str] = mapped_column(Text)
    legal_basis: Mapped[str] = mapped_column(String(100))
    reviewed_by: Mapped[str] = mapped_column(String(36))


class LicenseGrant(Timestamped):
    __tablename__ = "license_grants"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    purpose: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("license_evidence.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, default="")


class UploadSession(Timestamped):
    __tablename__ = "upload_sessions"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    declared_size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="initiated")
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[bytes | None] = mapped_column(nullable=True)


class IngestBatch(Timestamped):
    __tablename__ = "ingest_batches"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default="created")
    totals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IngestItem(Timestamped):
    __tablename__ = "ingest_batch_items"
    batch_id: Mapped[str] = mapped_column(ForeignKey("ingest_batches.id"), index=True)
    upload_session_id: Mapped[str] = mapped_column(ForeignKey("upload_sessions.id"))
    asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class AssetBlob(Timestamped):
    __tablename__ = "asset_blobs"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(120))


class Asset(Timestamped):
    __tablename__ = "assets"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    blob_id: Mapped[str] = mapped_column(ForeignKey("asset_blobs.id"))
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(40))
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ingestion_status: Mapped[str] = mapped_column(String(30), default="registered")
    quality_status: Mapped[str] = mapped_column(String(30), default="unreviewed")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DiscoveryCandidate(Timestamped):
    __tablename__ = "discovery_candidates"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default="candidate")


class PipelineTemplate(Timestamped):
    __tablename__ = "pipeline_templates"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    template_type: Mapped[str] = mapped_column(String(50))


class PipelineVersion(Timestamped):
    __tablename__ = "pipeline_versions"
    template_id: Mapped[str] = mapped_column(ForeignKey("pipeline_templates.id"), index=True)
    semver: Mapped[str] = mapped_column(String(30))
    dag_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    dag_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="active")


class OperatorDefinition(Timestamped):
    __tablename__ = "operator_definitions"
    operator_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40))
    adapter_kind: Mapped[str] = mapped_column(String(40), default="builtin")
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    params_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("operator_key", "version", name="uq_operator_version"),)


class ProcessingBatch(Timestamped):
    __tablename__ = "processing_batches"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    __table_args__ = (
        Index(
            "uq_processing_batch_idempotency",
            "workspace_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class PipelineRun(Timestamped):
    __tablename__ = "pipeline_runs"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("processing_batches.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    pipeline_version_id: Mapped[str] = mapped_column(ForeignKey("pipeline_versions.id"))
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NodeRun(Timestamped):
    __tablename__ = "node_runs"
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(100))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    log_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    operator_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_count: Mapped[int] = mapped_column(Integer, default=0)
    output_count: Mapped[int] = mapped_column(Integer, default=0)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    __table_args__ = (UniqueConstraint("run_id", "node_id", "attempt_no", name="uq_node_attempt"),)


class Artifact(Timestamped):
    __tablename__ = "artifacts"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    storage_key: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(Timestamped):
    __tablename__ = "documents"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    parse_status: Mapped[str] = mapped_column(String(30), default="succeeded")


class DocumentVersion(Timestamped):
    __tablename__ = "document_versions"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    content_sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(50), default="builtin-1")
    parser_name: Mapped[str] = mapped_column(String(80), default="builtin")
    config_hash: Mapped[str] = mapped_column(String(64), default="")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="succeeded")


class Segment(Timestamped):
    __tablename__ = "segments"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    quality_state: Mapped[str] = mapped_column(String(30), default="reviewed")
    location_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)


class QualityIssue(Timestamped):
    __tablename__ = "quality_issues"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    reason: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(50), default="builtin-1")


class QualityReview(Timestamped):
    __tablename__ = "quality_reviews"
    issue_id: Mapped[str] = mapped_column(ForeignKey("quality_issues.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(36))
    decision: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="")


class QualityRuleSet(Timestamped):
    __tablename__ = "quality_rule_sets"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    product_type: Mapped[str] = mapped_column(String(30), default="*")
    status: Mapped[str] = mapped_column(String(30), default="active")


class QualityRuleVersion(Timestamped):
    __tablename__ = "quality_rule_versions"
    rule_set_id: Mapped[str] = mapped_column(ForeignKey("quality_rule_sets.id"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_by: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("rule_set_id", "version", name="uq_quality_rule_version"),)


class QualityEvaluationRun(Timestamped):
    __tablename__ = "quality_evaluation_runs"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    rule_set_id: Mapped[str] = mapped_column(ForeignKey("quality_rule_sets.id"), index=True)
    rule_version_id: Mapped[str] = mapped_column(ForeignKey("quality_rule_versions.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    product_type: Mapped[str] = mapped_column(String(30), default="*")
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    metric_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(36))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class QualityMetricResult(Timestamped):
    __tablename__ = "quality_metric_results"
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("quality_evaluation_runs.id"), index=True
    )
    metric_id: Mapped[str] = mapped_column(String(120), index=True)
    metric_version: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(40))
    value_numeric: Mapped[float | None] = mapped_column(nullable=True)
    numerator: Mapped[float | None] = mapped_column(nullable=True)
    denominator: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str] = mapped_column(String(40), default="ratio")
    direction: Mapped[str] = mapped_column(String(20), default="higher_is_better")
    threshold_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="NOT_EVALUATED")
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DatasetQualityReport(Timestamped):
    __tablename__ = "dataset_quality_reports"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("quality_evaluation_runs.id"), index=True
    )
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    report_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="final")
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "evaluation_run_id", name="uq_dataset_quality_report"
        ),
    )


class DatasetVersionComparison(Timestamped):
    __tablename__ = "dataset_version_comparisons"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    left_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    right_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    comparison_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    created_by: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint(
            "left_version_id", "right_version_id", name="uq_dataset_version_comparison"
        ),
    )


class Dataset(Timestamped):
    __tablename__ = "dataset_definitions"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160))
    product_type: Mapped[str] = mapped_column(String(30), default="sft")


class DatasetBuild(Timestamped):
    __tablename__ = "dataset_builds"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_definitions.id"), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="snapshot_locked")
    validated_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class BuildInput(Timestamped):
    __tablename__ = "dataset_build_inputs"
    build_id: Mapped[str] = mapped_column(ForeignKey("dataset_builds.id"), index=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    content_sha256: Mapped[str] = mapped_column(String(64))


class CandidateSample(Timestamped):
    __tablename__ = "candidate_samples"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    build_id: Mapped[str] = mapped_column(ForeignKey("dataset_builds.id"), index=True)
    sample_key: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    __table_args__ = (UniqueConstraint("build_id", "sample_key", name="uq_candidate_key"),)


class SampleEvidence(Timestamped):
    __tablename__ = "sample_evidence"
    candidate_sample_id: Mapped[str] = mapped_column(ForeignKey("candidate_samples.id"), index=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), index=True)


class SampleReview(Timestamped):
    __tablename__ = "sample_reviews"
    candidate_sample_id: Mapped[str] = mapped_column(ForeignKey("candidate_samples.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(36))
    decision: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")


class DatasetVersion(Timestamped):
    __tablename__ = "dataset_versions"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_definitions.id"), index=True)
    build_id: Mapped[str] = mapped_column(ForeignKey("dataset_builds.id"))
    version: Mapped[str] = mapped_column(String(60))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="published")
    published_by: Mapped[str] = mapped_column(String(36))
    manifest_storage_key: Mapped[str] = mapped_column(Text, default="")
    content_storage_key: Mapped[str] = mapped_column(Text, default="")
    content_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    train_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_count: Mapped[int] = mapped_column(Integer, default=0)
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    tokenizer_version: Mapped[str] = mapped_column(String(80), default="builtin-whitespace-1")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)


class DatasetVersionSample(Timestamped):
    __tablename__ = "dataset_version_samples"
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    candidate_sample_id: Mapped[str] = mapped_column(ForeignKey("candidate_samples.id"), index=True)
    split: Mapped[str] = mapped_column(String(20))


class DatasetVersionArtifact(Timestamped):
    __tablename__ = "dataset_version_artifacts"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    content_sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)


class LineageEdge(Timestamped):
    __tablename__ = "lineage_edges"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    from_type: Mapped[str] = mapped_column(String(60), index=True)
    from_id: Mapped[str] = mapped_column(String(36), index=True)
    to_type: Mapped[str] = mapped_column(String(60), index=True)
    to_id: Mapped[str] = mapped_column(String(36), index=True)
    relation: Mapped[str] = mapped_column(String(80))


class OutboxEvent(Timestamped):
    __tablename__ = "outbox_events"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("aggregate_type", "aggregate_id", "event_type", name="uq_outbox_event"),
    )


class ExecutionLog(Timestamped):
    __tablename__ = "execution_logs"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    node_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)


class RagIndexVersion(Timestamped):
    __tablename__ = "rag_index_versions"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    request_key: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    content_sha256: Mapped[str] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("workspace_id", "request_key", name="uq_rag_index_request"),)


class RagChunk(Timestamped):
    __tablename__ = "rag_chunks"
    index_version_id: Mapped[str] = mapped_column(ForeignKey("rag_index_versions.id"), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    sample_id: Mapped[str] = mapped_column(ForeignKey("candidate_samples.id"))
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("index_version_id", "sample_id", name="uq_rag_chunk"),
        Index(
            "ix_rag_chunks_fts", sql_text("to_tsvector('simple', text)"), postgresql_using="gin"
        ).ddl_if(dialect="postgresql"),
    )


class RetrievalTrace(Timestamped):
    __tablename__ = "retrieval_traces"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    index_version_id: Mapped[str] = mapped_column(ForeignKey("rag_index_versions.id"))
    created_by: Mapped[str] = mapped_column(String(36))
    query: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)


class RagEvaluationSuite(Timestamped):
    __tablename__ = "rag_evaluation_suites"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    name: Mapped[str] = mapped_column(String(160))
    cases: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    reviewed_by: Mapped[str] = mapped_column(String(36))
    annotation_note: Mapped[str] = mapped_column(Text)


class RagEvaluationRun(Timestamped):
    __tablename__ = "rag_evaluation_runs"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    suite_id: Mapped[str] = mapped_column(ForeignKey("rag_evaluation_suites.id"))
    index_version_id: Mapped[str] = mapped_column(ForeignKey("rag_index_versions.id"))
    request_key: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(String(36))
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (UniqueConstraint("workspace_id", "request_key", name="uq_rag_eval_request"),)


class RagFeedback(Timestamped):
    __tablename__ = "rag_feedback"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("retrieval_traces.id"))
    evaluation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("rag_evaluation_runs.id"), nullable=True
    )
    case_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"))
    quality_issue_id: Mapped[str] = mapped_column(ForeignKey("quality_issues.id"))
    category: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36))


class RetrievalReview(Timestamped):
    __tablename__ = "retrieval_reviews"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("retrieval_traces.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_key: Mapped[str] = mapped_column(String(120))
    rubric_version: Mapped[str] = mapped_column(String(50), default="evidence-review.v1")
    ratings: Mapped[dict[str, Any]] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("workspace_id", "request_key", name="uq_retrieval_review_request"),
    )


class IngestPlan(Timestamped):
    __tablename__ = "ingest_plans"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    request_key: Mapped[str] = mapped_column(String(120))
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    review_note: Mapped[str] = mapped_column(Text, default="")
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (
        UniqueConstraint("workspace_id", "request_key", name="uq_ingest_plan_request"),
    )


class GenerationRun(Timestamped):
    __tablename__ = "generation_runs"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("retrieval_traces.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    call_reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (
        UniqueConstraint("workspace_id", "request_key", name="uq_generation_request"),
    )
