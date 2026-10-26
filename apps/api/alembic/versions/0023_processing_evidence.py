"""Persist step evidence and stable logical record mappings for M1 processing."""

import sqlalchemy as sa
from alembic import op

revision = "0023_processing_evidence"
down_revision = "0022_metadata_schema_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    node_columns = {column["name"] for column in inspector.get_columns("node_runs")}
    with op.batch_alter_table("node_runs") as batch:
        for column in ("input_count", "output_count", "filtered_count"):
            if column in node_columns:
                batch.alter_column(column, existing_type=sa.Integer(), nullable=True)
        additions = {
            "modified_count": sa.Column("modified_count", sa.Integer(), nullable=True),
            "failed_count": sa.Column("failed_count", sa.Integer(), nullable=True),
            "input_unit": sa.Column("input_unit", sa.String(20), nullable=True),
            "output_unit": sa.Column("output_unit", sa.String(20), nullable=True),
            "input_refs": sa.Column("input_refs", sa.JSON(), nullable=True),
            "output_refs": sa.Column("output_refs", sa.JSON(), nullable=True),
            "started_at": sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            "completed_at": sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        }
        for name, column in additions.items():
            if name not in node_columns:
                batch.add_column(column)

    segment_columns = {column["name"] for column in inspector.get_columns("segments")}
    segment_indexes = {index["name"] for index in inspector.get_indexes("segments")}
    with op.batch_alter_table("segments") as batch:
        if "record_key" not in segment_columns:
            batch.add_column(sa.Column("record_key", sa.String(255), nullable=True))
        if "ix_segments_record_key" not in segment_indexes:
            batch.create_index("ix_segments_record_key", ["record_key"])

    if "processing_record_maps" not in inspector.get_table_names():
        op.create_table(
            "processing_record_maps",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
            sa.Column("node_run_id", sa.String(36), sa.ForeignKey("node_runs.id"), nullable=False),
            sa.Column("record_id", sa.String(255), nullable=False),
            sa.Column("before_segment_id", sa.String(36), nullable=True),
            sa.Column("after_segment_id", sa.String(36), nullable=True),
            sa.Column("before_hash", sa.String(64), nullable=True),
            sa.Column("after_hash", sa.String(64), nullable=True),
            sa.UniqueConstraint("node_run_id", "record_id", name="uq_processing_record_map"),
        )
        for name, column in {
            "ix_processing_record_maps_workspace_id": ["workspace_id"],
            "ix_processing_record_maps_run_id": ["run_id"],
            "ix_processing_record_maps_node_run_id": ["node_run_id"],
            "ix_processing_record_maps_record_id": ["record_id"],
            "ix_processing_record_maps_before_segment_id": ["before_segment_id"],
            "ix_processing_record_maps_after_segment_id": ["after_segment_id"],
        }.items():
            op.create_index(name, "processing_record_maps", column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "processing_record_maps" in inspector.get_table_names():
        op.drop_table("processing_record_maps")
    segment_columns = {column["name"] for column in inspector.get_columns("segments")}
    segment_indexes = {index["name"] for index in inspector.get_indexes("segments")}
    with op.batch_alter_table("segments") as batch:
        if "ix_segments_record_key" in segment_indexes:
            batch.drop_index("ix_segments_record_key")
        if "record_key" in segment_columns:
            batch.drop_column("record_key")
    node_columns = {column["name"] for column in inspector.get_columns("node_runs")}
    with op.batch_alter_table("node_runs") as batch:
        for column in (
            "completed_at",
            "started_at",
            "output_refs",
            "input_refs",
            "output_unit",
            "input_unit",
            "failed_count",
            "modified_count",
        ):
            if column in node_columns:
                batch.drop_column(column)
        for column in ("input_count", "output_count", "filtered_count"):
            if column in node_columns:
                batch.alter_column(column, existing_type=sa.Integer(), nullable=False)
