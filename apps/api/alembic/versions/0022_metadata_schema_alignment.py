"""Align metadata tables with the existing JSONB/non-null timestamp model.

Keep 0021 unchanged for already-upgraded databases. Missing historical timestamps
must be repaired from evidence before upgrading; never synthesize them here.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0022_metadata_schema_alignment"
down_revision = "0021_metadata_proposals"
branch_labels = None
depends_on = None

JSON_COLUMNS = {
    "document_metadata": ("authors", "keywords"),
    "metadata_proposals": ("fields", "field_sources", "confidence"),
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Check both tables before applying any schema change.
    for table in JSON_COLUMNS:
        missing = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE created_at IS NULL OR updated_at IS NULL")
        ).scalar_one()
        if missing:
            raise RuntimeError(f"LEGACY_TIMESTAMP_MISSING: {table}; migration rolled back")
    for table, columns in JSON_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, type_=JSONB(), postgresql_using=f"{column}::jsonb")
        for column in ("created_at", "updated_at"):
            op.alter_column(table, column, nullable=False)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, columns in JSON_COLUMNS.items():
        for column in ("created_at", "updated_at"):
            op.alter_column(table, column, nullable=True)
        for column in columns:
            op.alter_column(table, column, type_=sa.JSON(), postgresql_using=f"{column}::json")
