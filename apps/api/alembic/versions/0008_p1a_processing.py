"""P1-A operator registry, node metrics and immutable document processing versions."""

from alembic import op
import sqlalchemy as sa

revision = "0008_p1a_processing"
down_revision = "0007_execution_timing"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _add(bind, table: str, name: str, column: sa.Column) -> None:
    if name not in _columns(bind, table):
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    if "operator_definitions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "operator_definitions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("operator_key", sa.String(120), nullable=False),
            sa.Column("version", sa.String(40), nullable=False),
            sa.Column("adapter_kind", sa.String(40), nullable=False, server_default="builtin"),
            sa.Column("input_schema", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("output_schema", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("params_schema", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("operator_key", "version", name="uq_operator_version"),
        )
        op.create_index("ix_operator_definitions_operator_key", "operator_definitions", ["operator_key"])
    for name, column in (
        ("operator_key", sa.Column("operator_key", sa.String(120), nullable=True)),
        ("operator_version", sa.Column("operator_version", sa.String(40), nullable=True)),
        ("config_snapshot", sa.Column("config_snapshot", sa.JSON(), nullable=True)),
        ("input_count", sa.Column("input_count", sa.Integer(), nullable=True)),
        ("output_count", sa.Column("output_count", sa.Integer(), nullable=True)),
        ("filtered_count", sa.Column("filtered_count", sa.Integer(), nullable=True)),
        ("duration_ms", sa.Column("duration_ms", sa.Float(), nullable=True)),
        ("failure_code", sa.Column("failure_code", sa.String(80), nullable=True)),
    ):
        _add(bind, "node_runs", name, column)
    for name, column in (
        ("parser_name", sa.Column("parser_name", sa.String(80), nullable=True)),
        ("config_hash", sa.Column("config_hash", sa.String(64), nullable=True)),
        ("run_id", sa.Column("run_id", sa.String(36), nullable=True)),
        ("artifact_id", sa.Column("artifact_id", sa.String(36), nullable=True)),
        ("status", sa.Column("status", sa.String(30), nullable=True)),
    ):
        _add(bind, "document_versions", name, column)
    for name, column in (
        ("location_json", sa.Column("location_json", sa.JSON(), nullable=True)),
        ("token_count", sa.Column("token_count", sa.Integer(), nullable=True)),
        ("section_title", sa.Column("section_title", sa.String(255), nullable=True)),
    ):
        _add(bind, "segments", name, column)
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("UPDATE node_runs SET input_count=0 WHERE input_count IS NULL"))
        op.execute(sa.text("UPDATE node_runs SET output_count=0 WHERE output_count IS NULL"))
        op.execute(sa.text("UPDATE node_runs SET filtered_count=0 WHERE filtered_count IS NULL"))
        op.execute(sa.text("UPDATE node_runs SET config_snapshot='{}'::jsonb WHERE config_snapshot IS NULL"))
        op.execute(sa.text("UPDATE document_versions SET parser_name='builtin' WHERE parser_name IS NULL"))
        op.execute(sa.text("UPDATE document_versions SET config_hash='' WHERE config_hash IS NULL"))
        op.execute(sa.text("UPDATE document_versions SET status='succeeded' WHERE status IS NULL"))
        op.execute(sa.text("UPDATE segments SET location_json='{}'::jsonb WHERE location_json IS NULL"))
        op.execute(sa.text("UPDATE segments SET token_count=0 WHERE token_count IS NULL"))
    else:
        for table, column, value in (
            ("node_runs", "input_count", 0), ("node_runs", "output_count", 0),
            ("node_runs", "filtered_count", 0), ("node_runs", "config_snapshot", {}),
            ("document_versions", "parser_name", "builtin"), ("document_versions", "config_hash", ""),
            ("document_versions", "status", "succeeded"), ("segments", "location_json", {}),
            ("segments", "token_count", 0),
        ):
            op.execute(sa.text(f"UPDATE {table} SET {column} = :value WHERE {column} IS NULL").bindparams(value=value))
    for table, name in (("node_runs", "input_count"), ("node_runs", "output_count"),
                        ("node_runs", "filtered_count"), ("segments", "token_count")):
        op.alter_column(table, name, nullable=False)
    op.alter_column("node_runs", "config_snapshot", nullable=False, server_default="{}")
    op.alter_column("document_versions", "parser_name", nullable=False, server_default="builtin")
    op.alter_column("document_versions", "config_hash", nullable=False, server_default="")
    op.alter_column("document_versions", "status", nullable=False, server_default="succeeded")
    op.alter_column("segments", "location_json", nullable=False, server_default="{}")


def downgrade() -> None:
    bind = op.get_bind()
    for table, name in (("segments", "section_title"), ("segments", "token_count"),
                        ("segments", "location_json"), ("document_versions", "status"),
                        ("document_versions", "artifact_id"), ("document_versions", "run_id"),
                        ("document_versions", "config_hash"), ("document_versions", "parser_name"),
                        ("node_runs", "failure_code"), ("node_runs", "duration_ms"),
                        ("node_runs", "filtered_count"), ("node_runs", "output_count"),
                        ("node_runs", "input_count"), ("node_runs", "config_snapshot"),
                        ("node_runs", "operator_version"), ("node_runs", "operator_key")):
        if name in _columns(bind, table):
            op.drop_column(table, name)
    if "operator_definitions" in sa.inspect(bind).get_table_names():
        op.drop_table("operator_definitions")
