"""Persist DPO import request identity for replay-safe candidate ingestion."""

import sqlalchemy as sa
from alembic import op

revision = "0020_dpo_import_idempotency"
down_revision = "0019_dpo_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("preference_samples", sa.Column("import_request_key", sa.String(120)))
    op.add_column("preference_samples", sa.Column("import_request_hash", sa.String(64)))
    op.execute(
        "UPDATE preference_samples SET import_request_key = sample_key, "
        "import_request_hash = md5(sample_key)"
    )
    op.alter_column("preference_samples", "import_request_key", nullable=False)
    op.alter_column("preference_samples", "import_request_hash", nullable=False)
    op.create_index(
        "ix_preference_samples_import_request_key",
        "preference_samples",
        ["import_request_key"],
    )
    op.create_unique_constraint(
        "uq_preference_import_item",
        "preference_samples",
        ["workspace_id", "import_request_key", "sample_key"],
    )


def downgrade():
    op.drop_constraint("uq_preference_import_item", "preference_samples", type_="unique")
    op.drop_index("ix_preference_samples_import_request_key", table_name="preference_samples")
    op.drop_column("preference_samples", "import_request_hash")
    op.drop_column("preference_samples", "import_request_key")
