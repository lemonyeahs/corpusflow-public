"""Replay CI on fresh local volumes without touching the normal development stack."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from init_env import generate_values, write_env

ROOT = Path(__file__).resolve().parents[1]


def http_status(port: int, path: str, expected: int) -> dict:
    # Bound retries allow the real probe's dependency timeout to elapse on faults.
    for _ in range(20):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=15) as response:
                status, body = response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, json.load(exc)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
            continue
        if status == expected:
            return {"path": path, "status": status, "body": body}
        time.sleep(1)
    raise RuntimeError(f"{path} did not reach HTTP {expected}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--builder", help="Optional existing BuildKit builder; not modified or removed"
    )
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    context = json.loads(
        subprocess.check_output(
            ["docker", "context", "inspect"], text=True, encoding="utf-8", timeout=10
        )
    )[0]
    endpoint = os.environ.get("DOCKER_HOST") or context["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith(("unix://", "npipe://")):
        raise SystemExit("Verifier requires a local Docker socket")
    if shutil.disk_usage(ROOT).free < 15 * 1024**3:
        raise SystemExit("Verifier requires at least 15 GiB free before source builds")
    subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        check=True,
        timeout=20,
        stdout=subprocess.DEVNULL,
    )
    project = "cf-verify-" + uuid.uuid4().hex[:12]
    reports = (args.report_dir or ROOT / ".local" / project).resolve()
    reports.mkdir(parents=True, exist_ok=False)
    print(f"Isolated project: {project}; reports: {reports}", flush=True)
    sockets = [socket.socket() for _ in range(5)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        pg, redis, s3, console, api = [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()
    values = generate_values()
    values.update(
        APP_ENV="test",
        CF_POSTGRES_PORT=str(pg),
        CF_REDIS_PORT=str(redis),
        CF_S3_PORT=str(s3),
        CF_S3_CONSOLE_PORT=str(console),
        CF_API_PORT=str(api),
        DATABASE_URL=(
            f"postgresql+psycopg://corpusflow:{values['POSTGRES_PASSWORD']}"
            f"@127.0.0.1:{pg}/corpusflow"
        ),
        REDIS_URL=f"redis://:{values['REDIS_PASSWORD']}@127.0.0.1:{redis}/0",
        OBJECT_STORE_ENDPOINT=f"http://127.0.0.1:{s3}",
        OBJECT_STORE_BUCKET=project,
    )
    summary = {"project": project, "status": "running", "steps": [], "http": []}
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        env_file = Path(directory) / ".env"
        write_env(env_file, values)
        env = {
            **os.environ,
            **values,
            "CF_ENV_FILE": str(env_file),
            "CF_TEST_ADMIN_DATABASE_URL": values["DATABASE_URL"],
            "CF_TEST_OBJECT_STORE_ENDPOINT": values["OBJECT_STORE_ENDPOINT"],
            "CF_EXPECT_STORAGE_PERSISTENCE": "0",
            "COMPOSE_ANSI": "never",
            "BUILDKIT_PROGRESS": "plain",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
        compose = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "infra/compose.yaml"),
        ]

        def run(name: str, command: list[str], timeout: int = 1800) -> None:
            print(name, flush=True)
            # Redact generated credentials even when a dependency prints them on failure.
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            output = result.stdout
            for key in (
                "POSTGRES_PASSWORD",
                "REDIS_PASSWORD",
                "OBJECT_STORE_ACCESS_KEY",
                "OBJECT_STORE_SECRET_KEY",
            ):
                output = output.replace(values[key], "[REDACTED]")
            (reports / f"{name}.log").write_text(output, encoding="utf-8", newline="\n")
            summary["steps"].append({"name": name, "exit_code": result.returncode})
            if result.returncode:
                raise RuntimeError(f"{name} failed; see {reports / (name + '.log')}")

        try:
            run("install", ["uv", "sync", "--locked"])
            run("checks", ["make", "check"])
            # Contact official registries even when the engine has existing layers.
            run("pull", [*compose, "pull", "postgres", "redis"])
            build = [*compose, "build", "--pull", "--no-cache"]
            if args.builder:
                build += ["--builder", args.builder]
            # Avoid compiling MinIO alongside the API images on small developer hosts.
            run("build-minio", [*build, "minio"])
            run("build-api", [*build, "api", "init"])
            run(
                "up", [*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "180", "api"]
            )
            run("ps", [*compose, "ps", "--all"])
            run("migration-and-storage", ["make", "integration"])
            summary["http"].append(http_status(api, "/health", 200))
            summary["http"].append(http_status(api, "/ready", 200))
            # The fault injection touches only this random project's container.
            run("stop-minio", [*compose, "stop", "minio"])
            summary["http"].append(http_status(api, "/ready", 503))
            summary["http"].append(http_status(api, "/health", 200))
            run("start-minio", [*compose, "start", "minio"])
            summary["http"].append(http_status(api, "/ready", 200))
            # Verify persisted bytes as well as fresh multipart operations after restart.
            env["CF_EXPECT_STORAGE_PERSISTENCE"] = "1"
            run(
                "storage-after-restart",
                [
                    "uv",
                    "run",
                    "--locked",
                    "pytest",
                    "tests/integration/test_storage.py",
                    "-q",
                ],
            )
            run("minio-version", [*compose, "exec", "-T", "minio", "minio", "--version"])
            summary["status"] = "passed"
        finally:
            # Only resources created under this invocation's random name are disposable.
            # No --volumes, global prune, or mutation of the existing project is used.
            try:
                run("cleanup", [*compose, "down"], timeout=120)
            except Exception:
                summary["status"] = "cleanup_failed"
                raise
            finally:
                if summary["status"] == "running":
                    summary["status"] = "failed"
                summary["retained_test_volumes"] = [
                    project + suffix for suffix in ("_pg-data", "_redis-data", "_s3-data")
                ]
                (reports / "result.json").write_text(
                    json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
                )
    print(f"Full environment verification passed: {reports / 'result.json'}", flush=True)


if __name__ == "__main__":
    main()
