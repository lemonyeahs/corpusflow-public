"""Real M0 browser authentication against a new local PostgreSQL and API, never shared services."""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTGRES = (
    "postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="store_true", help="Also verify M1 catalog HTTP and UI")
    args = parser.parse_args()
    context = json.loads(
        subprocess.check_output(["docker", "context", "inspect"], encoding="utf-8", timeout=15)
    )[0]
    endpoint = os.environ.get("DOCKER_HOST") or context["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith(("npipe://", "unix://")):
        raise SystemExit("Only a local Docker daemon is supported")
    name = ("cf-m1-" if args.catalog else "cf-m0-") + uuid.uuid4().hex[:12]
    reports = ROOT / ".local" / name
    reports.mkdir(parents=True, exist_ok=False)
    password = secrets.token_hex(16)
    env = {
        **os.environ,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_USER": "m0",
        "POSTGRES_DB": "m0",
        "APP_ENV": "test",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "OBJECT_STORE_ENDPOINT": "http://127.0.0.1:1",
        "OBJECT_STORE_BUCKET": "m0-isolated",
        "OBJECT_STORE_ACCESS_KEY": "m0-isolated",
        "OBJECT_STORE_SECRET_KEY": "m0-isolated",
        "LLM_PROVIDER": "disabled",
        "LLM_API_KEY": "",
        "LLM_WORKSPACES": "[]",
        "TRAINING_CENTER_DATA_DIR": str(reports / "catalog"),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "MINIO_ROOT_USER": "m1-isolated",
        "MINIO_ROOT_PASSWORD": password,
    }
    summary = {
        "status": "running",
        "container": name,
        "checks": [],
        "not_run": [
            "Worker processing",
            "Redis readiness and processing APIs",
            "Worker-produced lineage",
        ],
    }

    def run(label, command, timeout=120):
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        (reports / f"{label}.log").write_text(
            result.stdout.replace(password, "[REDACTED]"), encoding="utf-8", newline="\n"
        )
        summary["checks"].append({"name": label, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{label} failed; see {reports / (label + '.log')}")
        return result.stdout.strip()

    server = None
    created = False
    storage_created = False
    try:
        run(
            "postgres-create",
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--label",
                "corpusflow.task=" + ("m1-verification" if args.catalog else "m0-verification"),
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                "POSTGRES_USER",
                "-e",
                "POSTGRES_DB",
                "-p",
                "127.0.0.1::5432",
                POSTGRES,
            ],
        )
        created = True
        port = run("postgres-port", ["docker", "port", name, "5432/tcp"]).rsplit(":", 1)[1]
        for _ in range(30):
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "m0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("isolated PostgreSQL did not become ready")
        env["DATABASE_URL"] = f"postgresql+psycopg://m0:{password}@127.0.0.1:{port}/m0"
        run("migrations", [sys.executable, "-m", "alembic", "upgrade", "head"])
        if args.catalog:
            # Use an already built local image by immutable ID; never touch shared containers.
            storage_image = run(
                "storage-image",
                [
                    "docker",
                    "image",
                    "inspect",
                    "corpusflow-p0a-minio:latest",
                    "--format",
                    "{{.Id}}",
                ],
            )
            run(
                "storage-create",
                [
                    "docker",
                    "run",
                    "-d",
                    "--pull=never",
                    "--name",
                    name + "-s3",
                    "--label",
                    "corpusflow.task=m1-verification",
                    "-e",
                    "MINIO_ROOT_USER",
                    "-e",
                    "MINIO_ROOT_PASSWORD",
                    "-p",
                    "127.0.0.1::9000",
                    storage_image,
                    "server",
                    "/data",
                ],
            )
            storage_created = True
            storage_port = run("storage-port", ["docker", "port", name + "-s3", "9000/tcp"]).rsplit(
                ":", 1
            )[1]
            env["OBJECT_STORE_ENDPOINT"] = f"http://127.0.0.1:{storage_port}"
            env["OBJECT_STORE_ACCESS_KEY"] = env["MINIO_ROOT_USER"]
            env["OBJECT_STORE_SECRET_KEY"] = password
            for _ in range(40):
                try:
                    urllib.request.urlopen(
                        env["OBJECT_STORE_ENDPOINT"] + "/minio/health/live", timeout=2
                    ).close()
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("isolated object store health timeout")
            run("storage-init", [sys.executable, "scripts/init_storage.py"])
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            api_port = sock.getsockname()[1]
        env["M0_LIVE_API"] = f"http://127.0.0.1:{api_port}"
        with (reports / "api.log").open("wb") as log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "corpusflow.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            for _ in range(40):
                try:
                    with urllib.request.urlopen(
                        env["M0_LIVE_API"] + "/health", timeout=2
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError("isolated API failed to start") from None
                    time.sleep(0.5)
            else:
                raise RuntimeError("isolated API health timeout")
            if args.catalog:
                env["M1_CATALOG_CONTEXT"] = str(reports / "browser-context.json")
                run(
                    "live-catalog-api",
                    [sys.executable, "scripts/check_training_center_http.py"],
                    timeout=300,
                )
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if not npm:
                raise RuntimeError("npm is required")
            run(
                "live-browser",
                [
                    npm,
                    "--prefix",
                    "apps/web",
                    "exec",
                    "--",
                    "playwright",
                    "test",
                    "--config",
                    "apps/web/playwright.m0-live.config.ts",
                ],
                timeout=240,
            )
        summary["status"] = "passed"
    finally:
        cleanup_errors = []
        try:
            if server is not None:
                server.terminate()
                server.wait(timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            cleanup_errors.append(type(exc).__name__ + ": owned API cleanup failed")
        try:
            if storage_created:
                run("stop-owned-storage", ["docker", "stop", name + "-s3"])
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            cleanup_errors.append(type(exc).__name__ + ": owned object storage cleanup failed")
        try:
            if created:
                run("stop-owned-postgres", ["docker", "stop", name])
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            cleanup_errors.append(type(exc).__name__ + ": owned PostgreSQL cleanup failed")
        if summary["status"] == "running":
            summary["status"] = "failed"
        if cleanup_errors:
            summary["status"] = "cleanup_failed"
            summary["cleanup_errors"] = cleanup_errors
        (reports / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            f"Training Center verification: {summary['status']}; report: {reports / 'result.json'}"
        )
        if cleanup_errors:
            raise RuntimeError("; ".join(cleanup_errors))


if __name__ == "__main__":
    main()
