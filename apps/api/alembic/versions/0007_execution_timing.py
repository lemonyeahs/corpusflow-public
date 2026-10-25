"""P0-I execution timing fields for operational metrics."""

import sqlalchemy as sa
from alembic import op

revision = "0007_execution_timing"
down_revision = "0006_system_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pipeline_runs")}
    for name in ("started_at", "finished_at"):
        if name not in columns:
            op.add_column(
                "pipeline_runs", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pipeline_runs")}
    for name in ("finished_at", "started_at"):
        if name in columns:
            op.drop_column("pipeline_runs", name)
