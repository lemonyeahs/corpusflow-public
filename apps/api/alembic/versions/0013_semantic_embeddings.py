"""Nullable immutable vectors on versioned chunks; existing lexical indexes unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_semantic_embeddings"
down_revision = "0012_legacy_schema_alignment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rag_chunks", sa.Column("embedding", sa.JSON().with_variant(JSONB, "postgresql")))


def downgrade():
    op.drop_column("rag_chunks", "embedding")
