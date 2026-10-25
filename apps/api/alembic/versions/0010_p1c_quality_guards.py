"""Complete P1-C indexes and protect append-only quality snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0010_p1c_quality_guards"
down_revision = "0009_p1c_quality_governance"
branch_labels = None
depends_on = None

TABLES = (
    "quality_rule_versions",
    "quality_metric_results",
    "dataset_quality_reports",
    "dataset_version_comparisons",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table, columns in {
        "quality_evaluation_runs": ("rule_set_id", "rule_version_id"),
        "dataset_quality_reports": ("evaluation_run_id",),
    }.items():
        existing = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        for column in columns:
            name = f"ix_{table}_{column}"
            if name not in existing:
                op.create_index(name, table, [column])
    if bind.dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION cf_quality_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'quality snapshot is immutable'; END $$;
        CREATE FUNCTION cf_quality_run_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.status IN ('succeeded', 'failed') THEN
            RAISE EXCEPTION 'completed quality evaluation is immutable';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER quality_run_immutable BEFORE UPDATE OR DELETE ON quality_evaluation_runs
          FOR EACH ROW EXECUTE FUNCTION cf_quality_run_immutable();
        """)
        for table in TABLES:
            op.execute(
                f"CREATE TRIGGER quality_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION cf_quality_immutable()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS quality_immutable ON {table}")
        op.execute("DROP TRIGGER IF EXISTS quality_run_immutable ON quality_evaluation_runs")
        op.execute("DROP FUNCTION IF EXISTS cf_quality_immutable()")
        op.execute("DROP FUNCTION IF EXISTS cf_quality_run_immutable()")
    # Indexes are retained at 0009: they are required by the declared model.
