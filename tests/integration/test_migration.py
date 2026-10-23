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
            monkeypatch.setenv("DATABASE_URL", test_url)
            config = Config("alembic.ini")
            engine = create_engine(test_url)
            try:
                command.upgrade(config, "head")
                with engine.connect() as conn:
                    assert (
                        conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        == "0001_p0a"
                    )
                command.check(config)
                command.downgrade(config, "base")
                with engine.connect() as conn:
                    assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 0
                command.upgrade(config, "head")
            finally:
                engine.dispose()
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
