"""Transactional outbox and execution logs."""

from alembic import op
from sqlalchemy import inspect

from corpusflow.db.session import Base
from corpusflow.db import models  # noqa: F401

revision = "0004_async_processing"
down_revision = "0003_immutable_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # create_all is safe for the newly introduced tables and preserves all P0 data.
    Base.metadata.create_all(bind=bind, tables=[models.OutboxEvent.__table__, models.ExecutionLog.__table__])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("execution_logs", "outbox_events"):
        if table in inspector.get_table_names():
            op.drop_table(table)
