"""Persist actual step start order; leave unknown historical order unmodified."""

import sqlalchemy as sa
from alembic import op

revision = "0024_execution_sequence"
down_revision = "0023_processing_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("node_runs")}
    if "execution_sequence" not in columns:
        op.add_column("node_runs", sa.Column("execution_sequence", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("node_runs", "execution_sequence")
