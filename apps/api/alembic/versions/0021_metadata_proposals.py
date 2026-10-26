"""Add confirmed metadata and auditable extraction proposals."""

import sqlalchemy as sa
from alembic import op

revision = "0021_metadata_proposals"
down_revision = "0020_dpo_import_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_metadata",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False, server_default="unidentified"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("research_field", sa.String(160), nullable=True),
        sa.Column("journal", sa.String(255), nullable=True),
        sa.Column("conference", sa.String(255), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("license_text", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id", "asset_id", name="uq_document_metadata_asset"),
    )
    op.create_index("ix_document_metadata_workspace_id", "document_metadata", ["workspace_id"])
    op.create_index("ix_document_metadata_asset_id", "document_metadata", ["asset_id"])
    op.create_index("ix_document_metadata_document_type", "document_metadata", ["document_type"])
    op.create_index(
        "ix_document_metadata_publication_year", "document_metadata", ["publication_year"]
    )
    op.create_index("ix_document_metadata_doi", "document_metadata", ["doi"])

    op.create_table(
        "metadata_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("field_sources", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sa.String(36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_metadata_proposals_workspace_id", "metadata_proposals", ["workspace_id"])
    op.create_index("ix_metadata_proposals_asset_id", "metadata_proposals", ["asset_id"])
    op.create_index("ix_metadata_proposals_status", "metadata_proposals", ["status"])
    op.create_index(
        "ix_metadata_proposals_asset_created", "metadata_proposals", ["asset_id", "created_at"]
    )


def downgrade():
    op.drop_table("metadata_proposals")
    op.drop_table("document_metadata")
