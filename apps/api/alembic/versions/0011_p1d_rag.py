"""Versioned RAG indexes, retrieval traces, evaluation and feedback."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_p1d_rag"
down_revision = "0010_p1c_quality_guards"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_index_versions",
        sa.Column("workspace_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column(
            "dataset_version_id",
            sa.String(36),
            sa.ForeignKey("dataset_versions.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("request_key", sa.String(120), nullable=False, primary_key=False),
        sa.Column(
            "config", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False, primary_key=False
        ),
        sa.Column("status", sa.String(30), nullable=False, primary_key=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, primary_key=False),
        sa.Column("error_code", sa.String(100), nullable=True, primary_key=False),
        sa.Column("created_by", sa.String(36), nullable=False, primary_key=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_rag_index_request"),
    )
    op.create_index("ix_rag_index_versions_workspace_id", "rag_index_versions", ["workspace_id"])
    op.create_table(
        "rag_chunks",
        sa.Column(
            "index_version_id",
            sa.String(36),
            sa.ForeignKey("rag_index_versions.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "sample_id",
            sa.String(36),
            sa.ForeignKey("candidate_samples.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "segment_id",
            sa.String(36),
            sa.ForeignKey("segments.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "asset_id", sa.String(36), sa.ForeignKey("assets.id"), nullable=False, primary_key=False
        ),
        sa.Column("text", sa.Text(), nullable=False, primary_key=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, primary_key=False),
        sa.Column(
            "provenance",
            sa.JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint("index_version_id", "sample_id", name="uq_rag_chunk"),
    )
    op.create_index("ix_rag_chunks_index_version_id", "rag_chunks", ["index_version_id"])
    op.create_table(
        "retrieval_traces",
        sa.Column("workspace_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column(
            "index_version_id",
            sa.String(36),
            sa.ForeignKey("rag_index_versions.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("created_by", sa.String(36), nullable=False, primary_key=False),
        sa.Column("query", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "config", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False, primary_key=False
        ),
        sa.Column(
            "result", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False, primary_key=False
        ),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index("ix_retrieval_traces_workspace_id", "retrieval_traces", ["workspace_id"])
    op.create_table(
        "rag_evaluation_suites",
        sa.Column("workspace_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column(
            "dataset_version_id",
            sa.String(36),
            sa.ForeignKey("dataset_versions.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("name", sa.String(160), nullable=False, primary_key=False),
        sa.Column(
            "cases", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False, primary_key=False
        ),
        sa.Column("content_sha256", sa.String(64), nullable=False, primary_key=False),
        sa.Column("reviewed_by", sa.String(36), nullable=False, primary_key=False),
        sa.Column("annotation_note", sa.Text(), nullable=False, primary_key=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index(
        "ix_rag_evaluation_suites_workspace_id", "rag_evaluation_suites", ["workspace_id"]
    )
    op.create_table(
        "rag_evaluation_runs",
        sa.Column("workspace_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column(
            "suite_id",
            sa.String(36),
            sa.ForeignKey("rag_evaluation_suites.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "index_version_id",
            sa.String(36),
            sa.ForeignKey("rag_index_versions.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("request_key", sa.String(120), nullable=False, primary_key=False),
        sa.Column("created_by", sa.String(36), nullable=False, primary_key=False),
        sa.Column(
            "config", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False, primary_key=False
        ),
        sa.Column("status", sa.String(30), nullable=False, primary_key=False),
        sa.Column(
            "report", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False, primary_key=False
        ),
        sa.Column("error_code", sa.String(100), nullable=True, primary_key=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_rag_eval_request"),
    )
    op.create_index("ix_rag_evaluation_runs_workspace_id", "rag_evaluation_runs", ["workspace_id"])
    op.create_table(
        "rag_feedback",
        sa.Column("workspace_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column(
            "trace_id",
            sa.String(36),
            sa.ForeignKey("retrieval_traces.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "evaluation_run_id",
            sa.String(36),
            sa.ForeignKey("rag_evaluation_runs.id"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("case_id", sa.String(80), nullable=True, primary_key=False),
        sa.Column(
            "segment_id",
            sa.String(36),
            sa.ForeignKey("segments.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "quality_issue_id",
            sa.String(36),
            sa.ForeignKey("quality_issues.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("category", sa.String(40), nullable=False, primary_key=False),
        sa.Column("note", sa.Text(), nullable=False, primary_key=False),
        sa.Column("created_by", sa.String(36), nullable=False, primary_key=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index("ix_rag_feedback_workspace_id", "rag_feedback", ["workspace_id"])
    op.execute(
        "CREATE INDEX ix_rag_chunks_fts ON rag_chunks USING gin(to_tsvector('simple', text))"
    )
    op.execute("""
    CREATE FUNCTION cf_rag_completed_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status = 'succeeded' THEN
        RAISE EXCEPTION 'completed RAG snapshot is immutable';
      END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute(
        "CREATE TRIGGER rag_immutable BEFORE UPDATE OR DELETE ON rag_index_versions "
        "FOR EACH ROW EXECUTE FUNCTION cf_rag_completed_immutable()"
    )
    op.execute(
        "CREATE TRIGGER rag_immutable BEFORE UPDATE OR DELETE ON rag_evaluation_runs "
        "FOR EACH ROW EXECUTE FUNCTION cf_rag_completed_immutable()"
    )
    op.execute(
        "CREATE TRIGGER rag_immutable BEFORE UPDATE OR DELETE ON rag_chunks "
        "FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
    )
    op.execute(
        "CREATE TRIGGER rag_immutable BEFORE UPDATE OR DELETE ON retrieval_traces "
        "FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
    )
    op.execute(
        "CREATE TRIGGER rag_immutable BEFORE UPDATE OR DELETE ON rag_evaluation_suites "
        "FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
    )


def downgrade():
    op.drop_table("rag_feedback")
    op.drop_table("rag_evaluation_runs")
    op.drop_table("rag_evaluation_suites")
    op.drop_table("retrieval_traces")
    op.drop_table("rag_chunks")
    op.drop_table("rag_index_versions")
    op.execute("DROP FUNCTION cf_rag_completed_immutable()")
