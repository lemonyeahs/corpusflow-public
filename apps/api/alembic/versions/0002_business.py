"""P0-B through P0-F domain tables.

The operation is idempotent so local databases created with the original
P0-A placeholder revision can be upgraded without a destructive reset.
"""

from alembic import op
from corpusflow.db import models  # noqa: F401
from corpusflow.db.session import Base

revision = "0002_business"
down_revision = "0001_p0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
