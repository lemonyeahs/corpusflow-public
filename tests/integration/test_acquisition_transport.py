"""Real loopback HTTPS bytes + MinIO + disposable PostgreSQL. NOT public acquisition evidence."""

import hashlib
import json
import os
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from corpusflow.adapters import acquisition as adapter
from corpusflow.adapters.storage import S3ObjectStore
from corpusflow.core.config import load_settings
from corpusflow.db.models import (
    Asset,
    DiscoveryCandidate,
    LicenseGrant,
    Membership,
    Source,
    User,
    Workspace,
)
from corpusflow.services import acquisition
from psycopg import sql
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

CONTENT = b"<html><h1>Original local acquisition fixture</h1><p>AES uses 128 bit blocks.</p></html>"


@pytest.fixture
def controlled_https(tmp_path, monkeypatch):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=fixture.test",
            "-addext",
            "subjectAltName=DNS:fixture.test",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/slow":
                time.sleep(0.25)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "https://169.254.169.254/")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            length = {"/truncated": len(CONTENT) + 20, "/large": 99999999, "/negative": -1}.get(
                self.path, len(CONTENT)
            )
            self.send_header("Content-Length", str(length))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(CONTENT)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_connect = socket.create_connection
    client_ctx = ssl.create_default_context(cafile=str(cert))
    targets = []

    def connect(address, **kwargs):
        targets.append(address)
        assert address in {
            ("127.0.0.1", 443),
            ("8.8.8.8", 443),
        }  # Pinned numeric target, no hostname DNS rebinding.
        return original_connect(("127.0.0.1", server.server_port), **kwargs)

    # Test-only transport injection: the production resolver remains fail-closed.
    monkeypatch.setattr(adapter, "public_addresses", lambda *a, **k: ["127.0.0.1"])
    monkeypatch.setattr(adapter.socket, "create_connection", connect)
    monkeypatch.setattr(adapter.ssl, "create_default_context", lambda: client_ctx)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    yield targets
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.mark.integration
def test_real_tls_redirect_size_and_truncation(controlled_https):
    fetch = adapter.SafeFetcher(["fixture.test"])
    result = fetch.get("https://fixture.test/ok")
    assert result.content == CONTENT and result.sha256 == hashlib.sha256(CONTENT).hexdigest()
    for path, code in [
        ("/redirect", "REDIRECT_REJECTED"),
        ("/large", "SIZE_LIMIT"),
        ("/truncated", "TRUNCATED"),
        ("/negative", "LENGTH_INVALID"),
    ]:
        with pytest.raises(adapter.AcquisitionError, match=code):
            fetch.get("https://fixture.test" + path)
    with pytest.raises(adapter.AcquisitionError, match="TIMEOUT"):
        adapter.SafeFetcher(["fixture.test"], timeout=0.05).get("https://fixture.test/slow")
    assert len(controlled_https) == 6


@pytest.mark.integration
def test_local_https_to_real_asset_minio_and_no_grants(controlled_https, monkeypatch):
    url_text = os.environ.get("CF_TEST_ADMIN_DATABASE_URL")
    if not url_text:
        pytest.skip("Explicit disposable local PostgreSQL required")
    url = make_url(url_text)
    assert url.host in {"127.0.0.1", "localhost"}
    name = "cf_ingest_" + uuid4().hex
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        engine = None
        try:
            testurl = url.set(database=name).render_as_string(hide_password=False)
            monkeypatch.setenv("DATABASE_URL", testurl)
            command.upgrade(Config("alembic.ini"), "head")
            engine = create_engine(testurl)
            cfg = load_settings().model_copy(update={"acquisition_hosts": ["fixture.test"]})
            with Session(engine) as db:
                w = Workspace(slug=name, name=name)
                a = User(oidc_sub=name + "a", display_name="fixture author")
                r = User(oidc_sub=name + "r", display_name="fixture reviewer")
                db.add_all([w, a, r])
                db.flush()
                db.add_all(
                    [
                        Membership(workspace_id=w.id, user_id=a.id, role="engineer"),
                        Membership(workspace_id=w.id, user_id=r.id, role="reviewer"),
                    ]
                )
                source = Source(workspace_id=w.id, name="CC0 local fixture")
                candidate = DiscoveryCandidate(
                    workspace_id=w.id, title="Original local fixture", url="https://fixture.test/ok"
                )
                db.add_all([source, candidate])
                db.flush()
                row = acquisition.create(db, cfg, w.id, a.id, source.id, [candidate.id], "test")
                row.reviewed_by = r.id
                row.review_note = "Original test bytes only"
                row.status = "running"
                acquisition.execute(db, cfg, row)
                db.commit()
                assert row.status == "succeeded" and len(row.results) == 1
                assert db.scalar(select(func.count(Asset.id))) == 1
                assert db.scalar(select(func.count(LicenseGrant.id))) == 0
                store = S3ObjectStore(
                    cfg.object_store_endpoint,
                    cfg.object_store_bucket,
                    cfg.object_store_access_key.get_secret_value(),
                    cfg.object_store_secret_key.get_secret_value(),
                )
                assert store.get(row.results[0]["object_key"]) == CONTENT
                # Terminal worker normally guards this; the service resumes from saved results.
                acquisition.execute(db, cfg, row)
                db.commit()
                assert db.scalar(select(func.count(Asset.id))) == 1
                Path(".local/closure").mkdir(parents=True, exist_ok=True)
                Path(".local/closure/controlled-ingest.json").write_text(
                    json.dumps(
                        {
                            "scope": (
                                "Controlled local HTTPS, injected DNS/CA/port in test only; "
                                "NOT public network"
                            ),
                            "asset": row.results,
                            "asset_count": 1,
                            "purpose_grant_count": 0,
                            "duplicates": 0,
                        },
                        indent=2,
                    )
                    + "\n"
                )
        finally:
            if engine:
                engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.mark.integration
def test_actual_peer_and_hostname_mismatch_are_rejected(controlled_https, monkeypatch):
    with pytest.raises(adapter.AcquisitionError, match="NETWORK_FAILED"):
        adapter.SafeFetcher(["wrong.test"]).get("https://wrong.test/ok")
    monkeypatch.setattr(adapter, "public_addresses", lambda *a, **k: ["8.8.8.8"])
    with pytest.raises(adapter.AcquisitionError, match="ADDRESS_REJECTED"):
        adapter.SafeFetcher(["fixture.test"]).get("https://fixture.test/ok")
