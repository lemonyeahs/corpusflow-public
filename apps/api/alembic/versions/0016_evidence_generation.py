"""Bounded asynchronous generation and durable at-most-once call reservations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016_evidence_generation"
down_revision = "0015_ingest_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("trace_id", sa.String(36), sa.ForeignKey("retrieval_traces.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("config_snapshot", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("call_reserved", sa.Boolean(), nullable=False),
        sa.Column("result", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_generation_request"),
    )
    op.create_index("ix_generation_runs_workspace_id", "generation_runs", ["workspace_id"])
    op.execute(
        "CREATE TRIGGER generation_immutable BEFORE UPDATE OR DELETE ON generation_runs "
        "FOR EACH ROW EXECUTE FUNCTION cf_rag_completed_immutable()"
    )


def downgrade():
    op.drop_table("generation_runs")
