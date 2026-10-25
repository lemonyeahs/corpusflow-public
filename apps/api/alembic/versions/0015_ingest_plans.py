"""Reviewed acquisition plans; original assets and purpose grants remain independent."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015_ingest_plans"
down_revision = "0014_retrieval_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingest_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("config_snapshot", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("results", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_ingest_plan_request"),
    )
    op.create_index("ix_ingest_plans_workspace_id", "ingest_plans", ["workspace_id"])
    op.execute("""CREATE FUNCTION cf_ingest_plan_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.status IN ('succeeded','rejected','failed') OR
           NEW.config_snapshot IS DISTINCT FROM OLD.config_snapshot OR
           NEW.created_by IS DISTINCT FROM OLD.created_by OR
           NEW.source_id IS DISTINCT FROM OLD.source_id OR
           NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR
           (OLD.reviewed_by IS NOT NULL AND (NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by
             OR NEW.review_note IS DISTINCT FROM OLD.review_note)) THEN
          RAISE EXCEPTION 'ingest plan snapshot is immutable';
        END IF;
        RETURN NEW;
      END $$;""")
    op.execute(
        "CREATE TRIGGER ingest_plan_guard BEFORE UPDATE ON ingest_plans "
        "FOR EACH ROW EXECUTE FUNCTION cf_ingest_plan_guard()"
    )


def downgrade():
    op.drop_table("ingest_plans")
    op.execute("DROP FUNCTION cf_ingest_plan_guard()")
