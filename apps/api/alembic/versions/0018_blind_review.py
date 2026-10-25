"""Frozen evaluation tasks and immutable reviewer assignments; scores reuse existing reviews."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018_blind_review"
down_revision = "0017_generation_guards"
branch_labels = None
depends_on = None


def upgrade():
    for name, columns in [
        (
            "review_tasks",
            [
                sa.Column(
                    "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
                ),
                sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
                sa.Column("request_key", sa.String(120), nullable=False),
                sa.Column("snapshot", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
                sa.Column("snapshot_sha256", sa.String(64), nullable=False),
                sa.UniqueConstraint("workspace_id", "request_key", name="uq_review_task_key"),
            ],
        ),
        (
            "review_assignments",
            [
                sa.Column(
                    "task_id", sa.String(36), sa.ForeignKey("review_tasks.id"), nullable=False
                ),
                sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
                sa.UniqueConstraint("task_id", "reviewer_id", name="uq_review_assignment"),
            ],
        ),
    ]:
        op.create_table(
            name,
            sa.Column("id", sa.String(36), primary_key=True),
            *columns,
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
        )
        op.execute(
            f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
        )
    op.create_index("ix_review_tasks_workspace_id", "review_tasks", ["workspace_id"])
    op.create_index("ix_review_assignments_task_id", "review_assignments", ["task_id"])


def downgrade():
    op.drop_table("review_assignments")
    op.drop_table("review_tasks")
