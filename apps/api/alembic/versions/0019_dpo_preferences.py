"""Persist DPO preference pairs and independent annotator decisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019_dpo_preferences"
down_revision = "0018_blind_review"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "preference_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("sample_key", sa.String(160), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_messages", sa.JSON().with_variant(JSONB, "postgresql")),
        sa.Column("response_a", sa.Text(), nullable=False),
        sa.Column("response_b", sa.Text(), nullable=False),
        sa.Column("chosen_response", sa.Text()),
        sa.Column("rejected_response", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("preference_reason", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("evidence_ids", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("candidate_model", sa.String(160)),
        sa.Column("model_version", sa.String(160)),
        sa.Column(
            "generation_config",
            sa.JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column("imported_by", sa.String(36), nullable=False),
        sa.Column("reviewed_by", sa.String(36)),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("annotation_version", sa.String(40), nullable=False),
        sa.Column("published_version_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("workspace_id", "sample_key", name="uq_preference_sample_key"),
    )
    op.create_index("ix_preference_samples_workspace_id", "preference_samples", ["workspace_id"])
    op.create_index("ix_preference_samples_status", "preference_samples", ["status"])
    op.create_index("ix_preference_samples_source_id", "preference_samples", ["source_id"])
    op.create_index(
        "ix_preference_samples_published_version_id", "preference_samples", ["published_version_id"]
    )

    op.create_table(
        "preference_annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column(
            "preference_sample_id",
            sa.String(36),
            sa.ForeignKey("preference_samples.id"),
            nullable=False,
        ),
        sa.Column("annotator_id", sa.String(36), nullable=False),
        sa.Column("choice", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("annotation_version", sa.String(40), nullable=False),
        sa.Column("presented_order", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "preference_sample_id",
            "annotator_id",
            name="uq_preference_annotation_annotator",
        ),
    )
    op.create_index(
        "ix_preference_annotations_workspace_id", "preference_annotations", ["workspace_id"]
    )
    op.create_index(
        "ix_preference_annotations_preference_sample_id",
        "preference_annotations",
        ["preference_sample_id"],
    )
    op.create_index(
        "ix_preference_annotations_annotator_id", "preference_annotations", ["annotator_id"]
    )
    op.execute(
        "CREATE TRIGGER preference_annotations_immutable BEFORE UPDATE OR DELETE "
        "ON preference_annotations FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
    )


def downgrade():
    op.execute("DROP TRIGGER preference_annotations_immutable ON preference_annotations")
    op.drop_table("preference_annotations")
    op.drop_table("preference_samples")
