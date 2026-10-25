"""Kill only an owned worker on a disposable DB and unique Redis queue, while SQL is blocked."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from corpusflow.core.config import load_settings
from psycopg import sql
from sqlalchemy.engine import make_url


def main():
    cfg = load_settings()
    url = make_url(cfg.database_url.get_secret_value())
    assert cfg.app_env in {"development", "test"} and url.host in {"localhost", "127.0.0.1"}
    tag = uuid4().hex[:12]
    dbname = "cf_crash_" + tag
    queue = "cf-crash-" + tag
    container = "cf-crash-worker-" + tag
    out = Path(".local/p2/crash-" + tag)
    out.mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    for key, value in cfg.model_dump().items():
        env[key.upper()] = (
            value.get_secret_value()
            if hasattr(value, "get_secret_value")
            else json.dumps(value)
            if isinstance(value, (list, dict))
            else str(value)
        )
    env.update(
        DATABASE_URL=url.set(database=dbname).render_as_string(hide_password=False),
        CF_TASK_QUEUE=queue,
        CF_BROKER_PREFIX=queue + ":",
        CF_VISIBILITY_TIMEOUT="5",
        LLM_PROVIDER="disabled",
        LLM_MAX_CALLS="0",
        LLM_WORKSPACES="[]",
        CF_API_URL=f"http://127.0.0.1:{port}/api/v1",
        CF_RAG_EVIDENCE_DIR=str(out.relative_to(Path.cwd())) if out.is_absolute() else str(out),
    )
    docker_env = {key: env[key] for key in cfg.model_dump().keys() for key in [key.upper()]}
    docker_env.update(
        CF_TASK_QUEUE=queue,
        CF_BROKER_PREFIX=queue + ":",
        CF_VISIBILITY_TIMEOUT="5",
        DEPENDENCY_TIMEOUT="10",
        DATABASE_URL=url.set(database=dbname, host="host.docker.internal").render_as_string(
            hide_password=False
        ),
        REDIS_URL=make_url(cfg.redis_url.get_secret_value())
        .set(host="host.docker.internal")
        .render_as_string(hide_password=False),
        OBJECT_STORE_ENDPOINT=cfg.object_store_endpoint.replace(
            "127.0.0.1", "host.docker.internal"
        ).replace("localhost", "host.docker.internal"),
        LLM_PROVIDER="disabled",
        LLM_MAX_CALLS="0",
        LLM_WORKSPACES="[]",
    )
    envfile = out / "worker.env"
    envfile.write_text("\n".join(f"{k}={v}" for k, v in docker_env.items()) + "\n")
    envfile.chmod(0o600)
    admin_dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    processes = []
    handles = []

    def start(args, name):
        handle = (out / name).open("w")
        handles.append(handle)
        p = subprocess.Popen(args, env=env, stdout=handle, stderr=subprocess.STDOUT)
        processes.append(p)
        return p

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env=env,
                check=True,
                capture_output=True,
            )
            start(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "corpusflow.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                "api.log",
            )
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container,
                    "--env-file",
                    str(envfile),
                    "corpusflow-p0a-worker",
                    "celery",
                    "-A",
                    "corpusflow.worker.celery_app:celery_app",
                    "worker",
                    "--pool=solo",
                    "--loglevel=WARNING",
                    "-Q",
                    queue,
                ],
                check=True,
                capture_output=True,
            )
            start([sys.executable, "scripts/dispatch_outbox.py"], "dispatcher.log")
            for _ in range(60):
                try:
                    if (
                        httpx.get(
                            f"http://127.0.0.1:{port}/ready", timeout=1, trust_env=False
                        ).status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            with (out / "seed.log").open("w") as log:
                subprocess.run(
                    [sys.executable, "scripts/verify_p1d_rag.py"],
                    env=env,
                    check=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=180,
                )
            fixture = json.loads((out / "web.json").read_text())
            who = fixture["session"]
            client = httpx.Client(
                base_url=env["CF_API_URL"],
                trust_env=False,
                timeout=15,
                headers={
                    "Authorization": f"Bearer {who['token']}",
                    "X-Workspace-ID": who["workspace_id"],
                },
            )
            dsn = url.set(drivername="postgresql", database=dbname).render_as_string(
                hide_password=False
            )
            with psycopg.connect(dsn) as blocker:
                blocker.execute("LOCK TABLE rag_chunks IN SHARE MODE")
                response = client.post(
                    "/rag/indexes",
                    json={
                        "dataset_version_id": fixture["dataset_version_id"],
                        "request_key": "crash-check",
                    },
                )
                assert response.status_code == 202, response.text
                iid = response.json()["index_version_id"]
                observed = None
                for _ in range(80):
                    waiting = admin.execute(
                        "SELECT state,wait_event,query FROM pg_stat_activity WHERE datname=%s "
                        "AND wait_event='relation' AND query ILIKE 'INSERT INTO rag_chunks%%'",
                        (dbname,),
                    ).fetchone()
                    if waiting:
                        observed = {
                            "state": waiting[0],
                            "wait_event": waiting[1],
                            "operation": "INSERT INTO rag_chunks",
                        }
                        break
                    time.sleep(0.1)
                assert observed, "Worker never reached the instrumented SQL write boundary"
                before = client.get(f"/rag/indexes/{iid}").json()
                assert before["status"] == "running" and before["chunk_count"] == 0, before
                subprocess.run(
                    ["docker", "kill", "--signal", "KILL", container],
                    check=True,
                    capture_output=True,
                )
                blocker.rollback()
            with psycopg.connect(dsn) as check:
                assert (
                    check.execute(
                        "SELECT count(*) FROM rag_chunks WHERE index_version_id=%s", (iid,)
                    ).fetchone()[0]
                    == 0
                )
            subprocess.run(["docker", "start", container], check=True, capture_output=True)
            for _ in range(180):
                result = client.get(f"/rag/indexes/{iid}").json()
                if result["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.5)
            assert result["status"] == "succeeded" and result["chunk_count"] == 26, result
            with psycopg.connect(dsn) as check:
                count = check.execute(
                    "SELECT count(*) FROM rag_chunks WHERE index_version_id=%s", (iid,)
                ).fetchone()[0]
                assert count == 26
            evidence = {
                "isolated_database": dbname,
                "isolated_queue": queue,
                "owned_worker": container,
                "observed_before_kill": observed,
                "before": before,
                "after_restart": result,
                "chunks_after_kill": 0,
                "chunks_after_recovery": count,
                "recovery": "Redis visibility timeout redelivery; no manually republished task",
                "shared_worker_killed": False,
            }
            Path(".local/p2/worker-crash-evidence.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                "PASS: owned worker killed during INSERT; rollback=0; automatic recovery=26 chunks"
            )
        finally:
            for p in processes:
                p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            for handle in handles:
                handle.close()
            # Only the randomly named database created above is removed.
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(dbname)))
            envfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
