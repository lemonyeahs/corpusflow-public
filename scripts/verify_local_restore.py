"""Real pg_dump/pg_restore against two random local databases, never an existing database."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from corpusflow.core.config import load_settings
from psycopg import sql
from sqlalchemy.engine import make_url


def main():
    cfg = load_settings()
    url = make_url(cfg.database_url.get_secret_value())
    assert url.host in {"localhost", "127.0.0.1"} and url.port == 55432
    tag = uuid4().hex[:12]
    names = ["cf_backup_" + tag, "cf_restore_" + tag]
    env = os.environ.copy()
    env["DATABASE_URL"] = url.set(database=names[0]).render_as_string(hide_password=False)
    backup = Path(".local/p2") / (names[0] + ".dump")
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as admin:
        created = []
        try:
            for name in names:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env=env,
                check=True,
                capture_output=True,
            )
            with psycopg.connect(
                url.set(drivername="postgresql", database=names[0]).render_as_string(
                    hide_password=False
                )
            ) as db:
                db.execute(
                    "INSERT INTO workspaces(id,slug,name,status,created_at,updated_at,revision) "
                    "VALUES ('owned-fixture','backup-fixture','Original backup fixture','active',"
                    "now(),now(),1)"
                )
            with backup.open("wb") as output:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "corpusflow-p0a-postgres-1",
                        "pg_dump",
                        "-U",
                        url.username,
                        "-d",
                        names[0],
                        "-Fc",
                    ],
                    stdout=output,
                    check=True,
                )
            with backup.open("rb") as source:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        "corpusflow-p0a-postgres-1",
                        "pg_restore",
                        "-U",
                        url.username,
                        "--no-owner",
                        "-d",
                        names[1],
                    ],
                    stdin=source,
                    check=True,
                    capture_output=True,
                )
            with psycopg.connect(
                url.set(drivername="postgresql", database=names[1]).render_as_string(
                    hide_password=False
                )
            ) as db:
                assert (
                    db.execute("SELECT name FROM workspaces WHERE id='owned-fixture'").fetchone()[0]
                    == "Original backup fixture"
                )
                revision = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                assert revision == "0018_blind_review"
                triggers = db.execute(
                    "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"
                ).fetchone()[0]
                assert triggers > 0
            evidence = {
                "source_database": names[0],
                "restored_database": names[1],
                "snapshot_bytes": backup.stat().st_size,
                "snapshot_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
                "revision": revision,
                "restored_user_triggers": triggers,
                "scope": "local schema/fixture restore; production RPO/RTO/MinIO NOT_VERIFIED",
            }
            Path(".local/p2/restore-evidence.json").write_text(
                json.dumps(evidence, indent=2) + "\n"
            )
            print("PASS: real pg_dump/pg_restore, fixture and immutable triggers preserved")
        finally:
            for name in reversed(created):
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            backup.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
