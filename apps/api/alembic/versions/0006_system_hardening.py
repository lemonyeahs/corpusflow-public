"""P0-I idempotency and reliability constraints."""

import sqlalchemy as sa
from alembic import op

revision = "0006_system_hardening"
down_revision = "0005_dataset_materialization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("processing_batches")}
    if "request_hash" not in columns:
        op.add_column("processing_batches", sa.Column("request_hash", sa.String(64), nullable=True))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("processing_batches")}
    if "uq_processing_batch_idempotency" not in indexes:
        if bind.dialect.name == "postgresql":
            op.create_index(
                "uq_processing_batch_idempotency",
                "processing_batches",
                ["workspace_id", "idempotency_key"],
                unique=True,
                postgresql_where=sa.text("idempotency_key IS NOT NULL"),
            )
        else:
            op.create_index(
                "uq_processing_batch_idempotency",
                "processing_batches",
                ["workspace_id", "idempotency_key"],
                unique=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("processing_batches")}
    if "uq_processing_batch_idempotency" in indexes:
        op.drop_index("uq_processing_batch_idempotency", table_name="processing_batches")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("processing_batches")}
    if "request_hash" in columns:
        op.drop_column("processing_batches", "request_hash")
