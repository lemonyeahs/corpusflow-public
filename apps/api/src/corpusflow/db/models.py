"""Persistent domain models for the P0 business loop.

The models deliberately use portable SQL types so the policy and state
machines can be exercised in disposable PostgreSQL and SQLite test databases.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON as SAJSON
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class ProcessingBatch(Timestamped):
    __tablename__ = "processing_batches"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")


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


class NodeRun(Timestamped):
    __tablename__ = "node_runs"
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(100))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    log_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class Segment(Timestamped):
    __tablename__ = "segments"
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    quality_state: Mapped[str] = mapped_column(String(30), default="reviewed")


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
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)


class DatasetVersionSample(Timestamped):
    __tablename__ = "dataset_version_samples"
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    candidate_sample_id: Mapped[str] = mapped_column(ForeignKey("candidate_samples.id"), index=True)
    split: Mapped[str] = mapped_column(String(20))


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
