"""Verify queued pipeline runs recover after the local worker is stopped."""

import json
import subprocess
import time
import urllib.request

from corpusflow.core.config import load_settings
from corpusflow.db.models import Asset, Membership, User
from corpusflow.db.session import build_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BASE = "http://127.0.0.1:58000/api/v1"


def call(method, path, token, body=None, workspace=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if workspace:
        headers["X-Workspace-ID"] = workspace
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def main():
    settings = load_settings()
    with sessionmaker(build_engine(settings), expire_on_commit=False)() as session:
        user = session.scalar(
            select(User)
            .where(User.oidc_sub.like("acceptance-admin-%"))
            .order_by(User.created_at.desc())
        )
        workspace = session.scalar(
            select(Membership.workspace_id).where(Membership.user_id == user.id)
        )
        asset = session.scalar(
            select(Asset).where(Asset.workspace_id == workspace).order_by(Asset.created_at.desc())
        )
        assert user and asset
    token = user.oidc_sub
    batch = call(
        "POST",
        "/pipeline-runs/batches",
        token,
        {"asset_ids": [asset.id, asset.id, asset.id]},
        workspace,
    )
    run_ids = [item["run_id"] for item in batch["accepted"]]
    subprocess.run(
        ["docker", "compose", "--env-file", ".env", "-f", "infra/compose.yaml", "stop", "worker"],
        check=True,
        capture_output=True,
    )
    time.sleep(2)
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            ".env",
            "-f",
            "infra/compose.yaml",
            "up",
            "-d",
            "worker",
        ],
        check=True,
        capture_output=True,
    )
    deadline = time.time() + 30
    statuses = []
    while time.time() < deadline:
        statuses = [
            call("GET", f"/pipeline-runs/{run_id}", token, workspace=workspace)["status"]
            for run_id in run_ids
        ]
        if all(status in {"succeeded", "failed"} for status in statuses):
            break
        time.sleep(1)
    assert statuses == ["succeeded", "succeeded", "succeeded"], statuses
    print("WORKER_RECOVERY PASS")
    print(json.dumps({"run_count": len(run_ids), "statuses": statuses, "worker_restarted": True}))


if __name__ == "__main__":
    main()
