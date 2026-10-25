"""Dataset materialization, manifest and immutable delivery metadata."""

import sqlalchemy as sa
from alembic import op
from corpusflow.db import models
from corpusflow.db.session import Base
from sqlalchemy import inspect

revision = "0005_dataset_materialization"
down_revision = "0004_async_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("dataset_builds")}
    if "validated_snapshot_hash" not in columns:
        op.add_column(
            "dataset_builds", models.DatasetBuild.__table__.c.validated_snapshot_hash.copy()
        )
    if "validated_by" not in columns:
        op.add_column("dataset_builds", models.DatasetBuild.__table__.c.validated_by.copy())
    version_columns = {c["name"] for c in inspector.get_columns("dataset_versions")}
    definitions = {
        "manifest_storage_key": sa.Text(),
        "content_storage_key": sa.Text(),
        "content_bytes": sa.Integer(),
        "sample_count": sa.Integer(),
        "train_count": sa.Integer(),
        "validation_count": sa.Integer(),
        "test_count": sa.Integer(),
        "token_count": sa.Integer(),
        "tokenizer_version": sa.String(80),
        "published_at": sa.DateTime(timezone=True),
    }
    for name, column_type in definitions.items():
        if name not in version_columns:
            op.add_column("dataset_versions", sa.Column(name, column_type, nullable=True))
            if name in {"manifest_storage_key", "content_storage_key", "tokenizer_version"}:
                default = "builtin-whitespace-1" if name == "tokenizer_version" else ""
                op.execute(
                    sa.text(f"UPDATE dataset_versions SET {name} = :value").bindparams(
                        value=default
                    )
                )
            elif name != "published_at":
                op.execute(sa.text(f"UPDATE dataset_versions SET {name} = 0"))
            if name != "published_at":
                op.alter_column("dataset_versions", name, nullable=False)
    Base.metadata.create_all(bind=bind, tables=[models.DatasetVersionArtifact.__table__])
    if bind.dialect.name == "postgresql":
        op.execute(
            """CREATE OR REPLACE FUNCTION corpusflow_immutable_dataset_version()
            RETURNS trigger AS $$
            BEGIN
              IF OLD.status = 'published' AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'published dataset version is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql"""
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "dataset_version_artifacts" in inspector.get_table_names():
        op.drop_table("dataset_version_artifacts")
    for name in (
        "published_at",
        "tokenizer_version",
        "token_count",
        "test_count",
        "validation_count",
        "train_count",
        "sample_count",
        "content_bytes",
        "content_storage_key",
        "manifest_storage_key",
    ):
        if name in {c["name"] for c in inspector.get_columns("dataset_versions")}:
            op.drop_column("dataset_versions", name)
    for name in ("validated_by", "validated_snapshot_hash"):
        if name in {c["name"] for c in inspector.get_columns("dataset_builds")}:
            op.drop_column("dataset_builds", name)
