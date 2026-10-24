"""Exercise P0-G release gates and isolated object-store failure paths."""

import json
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

from corpusflow.core.config import load_settings
from corpusflow.db.models import DatasetVersion, DatasetVersionArtifact, Membership, Segment, User
from corpusflow.db.session import build_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BASE = "http://127.0.0.1:58000/api/v1"


def call(method, path, token, body=None, workspace=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if workspace:
        headers["X-Workspace-ID"] = workspace
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def prepare(token, workspace, reviewer, segment_id, version):
    status, dataset = call(
        "POST", "/datasets", token, {"name": f"p0g-{uuid4().hex[:8]}"}, workspace
    )
    assert status == 200
    status, build = call(
        "POST",
        "/dataset-builds",
        token,
        {"dataset_id": dataset["dataset_id"], "segment_ids": [segment_id], "purpose": "training"},
        workspace,
    )
    assert status == 200
    candidates = call(
        "GET", f"/dataset-builds/{build['build_id']}/candidates", token, workspace=workspace
    )[1]
    sample_id = candidates["items"][0]["sample_id"]
    return dataset["dataset_id"], build["build_id"], sample_id, version


def approve_validate(token, workspace, reviewer, build_id, sample_id):
    assert (
        call(
            "POST",
            f"/candidate-samples/{sample_id}/reviews",
            reviewer,
            {"decision": "approved"},
            workspace,
        )[0]
        == 200
    )
    status, result = call(
        "POST", f"/dataset-builds/{build_id}/validate", token, workspace=workspace
    )
    assert status == 200 and result["ok"]


def main():
    settings = load_settings()
    factory = sessionmaker(build_engine(settings), expire_on_commit=False)
    with factory() as session:
        admin = session.scalar(
            select(User)
            .where(User.oidc_sub.like("acceptance-admin-%"))
            .order_by(User.created_at.desc())
        )
        workspace_ids = session.scalars(
            select(Membership.workspace_id).where(Membership.user_id == admin.id)
        ).all()
        latest = session.scalar(
            select(DatasetVersion)
            .where(DatasetVersion.workspace_id.in_(workspace_ids))
            .order_by(DatasetVersion.created_at.desc())
        )
        reviewer = session.scalar(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.oidc_sub.like("acceptance-reviewer-%"),
                Membership.workspace_id == latest.workspace_id if latest else False,
                Membership.role == "reviewer",
            )
            .order_by(User.created_at.desc())
        )
        segment = session.scalar(
            select(Segment)
            .where(Segment.workspace_id == latest.workspace_id)
            .order_by(Segment.created_at.desc())
        )
        assert admin and reviewer and latest and segment
        workspace = latest.workspace_id
    admin_token, reviewer_token = admin.oidc_sub, reviewer.oidc_sub

    dataset_id, build_id, sample_id, _ = prepare(
        admin_token, workspace, reviewer_token, segment.id, "9.0.0"
    )
    approve_validate(admin_token, workspace, reviewer_token, build_id, sample_id)
    with factory() as session:
        build = session.get(
            __import__("corpusflow.db.models", fromlist=["DatasetBuild"]).DatasetBuild, build_id
        )
        build.config_json = {"purpose": "training", "changed_after_validation": True}
        session.commit()
    status, result = call(
        "POST",
        f"/datasets/{dataset_id}/versions",
        admin_token,
        {"build_id": build_id, "version": "9.0.0"},
        workspace,
    )
    assert status == 409 and result["error"]["code"] == "BUILD_SNAPSHOT_CHANGED"

    dataset_id2, build_id2, sample_id2, _ = prepare(
        admin_token, workspace, reviewer_token, segment.id, "9.0.1"
    )
    status, result = call(
        "POST",
        f"/datasets/{dataset_id2}/versions",
        admin_token,
        {"build_id": build_id2, "version": "9.0.1"},
        workspace,
    )
    assert status == 409 and result["error"]["code"] == "RELEASE_GATE_FAILED"
    status, _ = call(
        "POST",
        f"/candidate-samples/{sample_id2}/reviews",
        admin_token,
        {"decision": "approved"},
        workspace,
    )
    assert status == 403

    dataset_id3, build_id3, sample_id3, _ = prepare(
        admin_token, workspace, reviewer_token, segment.id, "9.0.2"
    )
    approve_validate(admin_token, workspace, reviewer_token, build_id3, sample_id3)
    subprocess.run(
        ["docker", "compose", "--env-file", ".env", "-f", "infra/compose.yaml", "stop", "minio"],
        check=True,
        capture_output=True,
    )
    try:
        status, result = call(
            "POST",
            f"/datasets/{dataset_id3}/versions",
            admin_token,
            {"build_id": build_id3, "version": "9.0.2"},
            workspace,
        )
        assert status == 409 and result["error"]["code"] == "ADAPTER_UNAVAILABLE"
    finally:
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
                "minio",
            ],
            check=True,
            capture_output=True,
        )
        time.sleep(5)
    with factory() as session:
        assert (
            session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.dataset_id == dataset_id3, DatasetVersion.version == "9.0.2"
                )
            )
            is None
        )
    dataset_id4, build_id4, sample_id4, _ = prepare(
        admin_token, workspace, reviewer_token, segment.id, "9.0.3"
    )
    approve_validate(admin_token, workspace, reviewer_token, build_id4, sample_id4)
    conflict_key = f"datasets/{dataset_id4}/versions/9.0.3/dataset.jsonl"
    with factory() as session:
        existing = session.scalar(select(DatasetVersion).order_by(DatasetVersion.created_at.desc()))
        session.add(
            DatasetVersionArtifact(
                workspace_id=workspace,
                dataset_version_id=existing.id,
                kind="conflict-fixture",
                storage_key=conflict_key,
                content_sha256="0" * 64,
                byte_size=0,
            )
        )
        session.commit()
    status, _ = call(
        "POST",
        f"/datasets/{dataset_id4}/versions",
        admin_token,
        {"build_id": build_id4, "version": "9.0.3"},
        workspace,
    )
    print("db_conflict_response", status, _)
    assert status in {409, 500}
    with factory() as session:
        assert (
            session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.dataset_id == dataset_id4, DatasetVersion.version == "9.0.3"
                )
            )
            is None
        )
        fixture = session.scalar(
            select(DatasetVersionArtifact).where(DatasetVersionArtifact.storage_key == conflict_key)
        )
        session.delete(fixture)
        session.commit()
    print("DATASET_FAILURE_PATHS PASS")
    print(
        json.dumps(
            {
                "config_changed_blocked": True,
                "unreviewed_blocked": True,
                "self_approval_blocked": True,
                "minio_failure_no_version": True,
                "db_commit_failure_no_version": True,
            }
        )
    )


if __name__ == "__main__":
    main()
