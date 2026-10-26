"""Only uses a NEW random database on the explicitly opted-in local test server."""

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from corpusflow.db.models import (
    Asset,
    AssetBlob,
    DocumentMetadata,
    MetadataProposal,
    Source,
    Workspace,
)
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_upgrade_downgrade_reupgrade(monkeypatch):
    url_text = os.environ.get("CF_TEST_ADMIN_DATABASE_URL")
    if not url_text:
        pytest.skip("CF_TEST_ADMIN_DATABASE_URL absent: no disposable PostgreSQL configured")
    url = make_url(url_text)
    if url.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("Migration smoke test only accepts loopback test databases")
    name = "cf_smoke_" + uuid.uuid4().hex
    admin_dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            test_url = url.set(database=name).render_as_string(hide_password=False)
            test_url = test_url.replace("postgresql://", "postgresql+psycopg://", 1)
            monkeypatch.setenv("DATABASE_URL", test_url)
            config = Config("alembic.ini")
            # Require one head, but do not duplicate the latest revision ID in this test.
            head = ScriptDirectory.from_config(config).get_current_head()
            assert head is not None
            engine = create_engine(test_url)
            try:
                command.upgrade(config, "head")
                with engine.connect() as conn:
                    assert (
                        conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        == head
                    )
                command.check(config)
                # Reproduce an incremental legacy schema; empty-bootstrap success
                # alone cannot detect JSON/JSONB, nullability or missing-index drift.
                command.downgrade(config, "0011_p1d_rag")
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE operator_definitions ALTER COLUMN "
                            "input_schema TYPE json USING input_schema::json"
                        )
                    )
                    conn.execute(
                        text(
                            "ALTER TABLE operator_definitions ALTER COLUMN created_at DROP NOT NULL"
                        )
                    )
                    conn.execute(text("DROP INDEX ix_document_versions_run_id"))
                    conn.execute(
                        text("""INSERT INTO operator_definitions
                        (id, operator_key, version, adapter_kind, input_schema, output_schema,
                         params_schema, created_at, updated_at, revision)
                        VALUES ('legacy-check', 'fixture', '1', 'builtin',
                                json_build_object('text','原文','count',3),
                                '{}', '{}', NULL, now(), 1)
                    """)
                    )
                with pytest.raises(RuntimeError, match="LEGACY_TIMESTAMP_MISSING"):
                    command.upgrade(config, "head")
                with engine.begin() as conn:
                    assert (
                        conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        == "0011_p1d_rag"
                    )
                    # The test owns this row and has its known fixture timestamp.
                    conn.execute(
                        text(
                            "UPDATE operator_definitions SET created_at=updated_at "
                            "WHERE id='legacy-check'"
                        )
                    )
                command.upgrade(config, "head")
                command.check(config)
                with engine.connect() as conn:
                    assert conn.execute(
                        text(
                            "SELECT input_schema FROM operator_definitions WHERE id='legacy-check'"
                        )
                    ).scalar_one() == {"text": "原文", "count": 3}
                command.downgrade(config, "base")
                with engine.connect() as conn:
                    assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 0
                command.upgrade(config, "head")
                command.check(config)
                with engine.connect() as conn:
                    assert (
                        conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        == head
                    )
            finally:
                engine.dispose()
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def metadata_database(monkeypatch):
    url_text = os.environ.get("CF_TEST_ADMIN_DATABASE_URL")
    if not url_text:
        pytest.skip("CF_TEST_ADMIN_DATABASE_URL absent: no disposable PostgreSQL configured")
    url = make_url(url_text)
    if url.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("Migration smoke test only accepts loopback test databases")
    name = "cf_metadata_" + uuid.uuid4().hex
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        engine = None
        try:
            test_url = url.set(database=name).render_as_string(hide_password=False)
            monkeypatch.setenv("DATABASE_URL", test_url)
            engine = create_engine(test_url)
            config = Config("alembic.ini")
            command.upgrade(config, "0021_metadata_proposals")
            yield engine, config
        finally:
            if engine is not None:
                engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.mark.integration
@pytest.mark.parametrize("table", ["document_metadata", "metadata_proposals"])
@pytest.mark.parametrize("column", ["created_at", "updated_at"])
def test_metadata_alignment_preserves_values_and_blocks_missing_history(
    metadata_database, table, column
):
    engine, config = metadata_database
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    fields = {"title": "原文", "nested": {"count": 3, "values": ["a", "b"]}}
    with Session(engine) as session:
        workspace = Workspace(slug="migration-fixture", name="Migration fixture")
        session.add(workspace)
        session.flush()
        source = Source(workspace_id=workspace.id, name="Fixture")
        blob = AssetBlob(
            workspace_id=workspace.id,
            storage_key="migration-fixture",
            sha256="a" * 64,
            byte_size=1,
            media_type="text/plain",
        )
        session.add_all([source, blob])
        session.flush()
        asset = Asset(
            workspace_id=workspace.id,
            source_id=source.id,
            blob_id=blob.id,
            filename="fixture.txt",
            format="txt",
        )
        session.add(asset)
        session.flush()
        session.add_all(
            [
                DocumentMetadata(
                    id="metadata-fixture",
                    workspace_id=workspace.id,
                    asset_id=asset.id,
                    authors=["作者"],
                    keywords=["词一", "词二"],
                    confirmed_by="fixture-user",
                    created_at=stamp,
                    updated_at=stamp,
                ),
                MetadataProposal(
                    id="proposal-fixture",
                    workspace_id=workspace.id,
                    asset_id=asset.id,
                    fields=fields,
                    field_sources={"title": "heading"},
                    confidence={"title": 0.8},
                    created_at=stamp,
                    updated_at=stamp,
                ),
            ]
        )
        session.commit()
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {table} SET {column}=NULL"))
    with pytest.raises(RuntimeError, match=f"LEGACY_TIMESTAMP_MISSING: {table}"):
        command.upgrade(config, "head")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0021_metadata_proposals"
        )
        assert (
            conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='document_metadata' AND column_name='authors'"
                )
            ).scalar_one()
            == "json"
        )
        # Restore only this test-owned row's known timestamp.
        conn.execute(text(f"UPDATE {table} SET {column}=:stamp"), {"stamp": stamp})
    for _ in range(2):
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as session:
            metadata = session.get(DocumentMetadata, "metadata-fixture")
            proposal = session.get(MetadataProposal, "proposal-fixture")
            assert metadata.authors == ["作者"] and metadata.keywords == ["词一", "词二"]
            assert proposal.fields == fields
            assert proposal.field_sources == {"title": "heading"}
            assert proposal.confidence == {"title": 0.8}
            assert metadata.created_at == metadata.updated_at == stamp
            assert proposal.created_at == proposal.updated_at == stamp
        command.downgrade(config, "0021_metadata_proposals")
