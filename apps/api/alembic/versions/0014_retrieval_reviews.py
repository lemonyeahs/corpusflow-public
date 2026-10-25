"""Append-only individual reviews; no invented expert identities or scores."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014_retrieval_reviews"
down_revision = "0013_semantic_embeddings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retrieval_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("trace_id", sa.String(36), sa.ForeignKey("retrieval_traces.id"), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("rubric_version", sa.String(50), nullable=False),
        sa.Column("ratings", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_retrieval_review_request"),
    )
    op.create_index("ix_retrieval_reviews_workspace_id", "retrieval_reviews", ["workspace_id"])
    op.create_index("ix_retrieval_reviews_trace_id", "retrieval_reviews", ["trace_id"])
    op.execute(
        "CREATE TRIGGER review_immutable BEFORE UPDATE OR DELETE ON retrieval_reviews "
        "FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
    )


def downgrade():
    op.drop_table("retrieval_reviews")
