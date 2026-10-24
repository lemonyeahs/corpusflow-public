"""Protect published dataset content columns from mutation."""

from alembic import op

revision = "0003_immutable_release"
down_revision = "0002_business"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION corpusflow_immutable_dataset_version()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.status = 'published' AND (
                NEW.dataset_id <> OLD.dataset_id OR NEW.build_id <> OLD.build_id OR
                NEW.version <> OLD.version OR NEW.manifest_sha256 <> OLD.manifest_sha256 OR
                NEW.content_sha256 <> OLD.content_sha256 OR NEW.published_by <> OLD.published_by
              ) THEN
                RAISE EXCEPTION 'published dataset version is immutable';
              END IF;
              RETURN NEW;
            END $$;
            DROP TRIGGER IF EXISTS dataset_version_immutable ON dataset_versions;
            CREATE TRIGGER dataset_version_immutable
            BEFORE UPDATE ON dataset_versions
            FOR EACH ROW EXECUTE FUNCTION corpusflow_immutable_dataset_version();
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS dataset_version_immutable ON dataset_versions")
        op.execute("DROP FUNCTION IF EXISTS corpusflow_immutable_dataset_version()")
