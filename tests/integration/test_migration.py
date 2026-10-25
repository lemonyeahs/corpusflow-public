"""Only uses a NEW random database on the explicitly opted-in local test server."""

import os
import uuid

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


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
            engine = create_engine(test_url)
            try:
                command.upgrade(config, "head")
                with engine.connect() as conn:
                    assert (
                        conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        == "0013_semantic_embeddings"
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
            finally:
                engine.dispose()
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
