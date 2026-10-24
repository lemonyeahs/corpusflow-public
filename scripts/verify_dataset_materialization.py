"""Verify real dataset JSONL/Manifest delivery on the local Compose stack."""

import hashlib
import json
import urllib.error
import urllib.request

import boto3
from corpusflow.core.config import load_settings
from corpusflow.db.models import DatasetVersion, Membership, User
from corpusflow.db.session import build_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BASE = "http://127.0.0.1:58000/api/v1"


def request(
    method: str, path: str, token: str, body: dict | None = None, workspace: str | None = None
):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if workspace:
        headers["X-Workspace-ID"] = workspace
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> None:
    settings = load_settings()
    factory = sessionmaker(build_engine(settings), expire_on_commit=False)
    with factory() as session:
        user = session.scalar(
            select(User)
            .where(User.oidc_sub.like("acceptance-admin-%"))
            .order_by(User.created_at.desc())
        )
        workspace_ids = session.scalars(
            select(Membership.workspace_id).where(Membership.user_id == user.id)
        ).all()
        version = session.scalar(
            select(DatasetVersion)
            .where(DatasetVersion.workspace_id.in_(workspace_ids))
            .order_by(DatasetVersion.created_at.desc())
        )
        assert user and version
        workspace = version.workspace_id
        dataset_id = version.dataset_id
        build_id = version.build_id
        version_label = version.version
        content_key = version.content_storage_key
        content_sha = version.content_sha256
    token = user.oidc_sub
    status, versions = request(
        "GET", f"/datasets/{dataset_id}/versions", token, workspace=workspace
    )
    assert status == 200 and any(
        item["dataset_version_id"] == version.id for item in versions["items"]
    )
    status, manifest = request(
        "GET",
        f"/datasets/{dataset_id}/versions/{version_label}/manifest",
        token,
        workspace=workspace,
    )
    assert status == 200 and manifest["dataset_version_id"] == version.id
    status, download = request(
        "GET",
        f"/datasets/{dataset_id}/versions/{version_label}/download?purpose=training",
        token,
        workspace=workspace,
    )
    assert (
        status == 200
        and download["expires_in"] == 300
        and ("Signature=" in download["url"] or "X-Amz-Signature=" in download["url"])
    )
    status, duplicate = request(
        "POST",
        f"/datasets/{dataset_id}/versions",
        token,
        {"build_id": build_id, "version": version_label},
        workspace=workspace,
    )
    assert status == 200 and duplicate["idempotent"] is True
    client = boto3.client(
        "s3",
        endpoint_url=settings.object_store_endpoint,
        aws_access_key_id=settings.object_store_access_key.get_secret_value(),
        aws_secret_access_key=settings.object_store_secret_key.get_secret_value(),
        region_name="us-east-1",
    )
    try:
        body = client.get_object(Bucket=settings.object_store_bucket, Key=content_key)[
            "Body"
        ].read()
    finally:
        client.close()
    assert hashlib.sha256(body).hexdigest() == content_sha == manifest["content"]["sha256"]
    other_status, _ = request(
        "POST",
        "/auth/session",
        "unused",
        {
            "user_id": "p0g-cross-workspace",
            "display_name": "Cross",
            "workspace_name": "Cross Workspace",
        },
    )
    assert other_status == 200
    denied_status, denied = request(
        "GET", f"/datasets/{dataset_id}/versions/{version_label}/download", "p0g-cross-workspace"
    )
    assert denied_status == 404 and denied["error"]["code"] == "DATASET_VERSION_NOT_FOUND"
    print("DATASET_MATERIALIZATION PASS")
    print(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "dataset_version_id": version.id,
                "version": version_label,
                "jsonl_bytes": len(body),
                "sha256": content_sha,
                "signed_download": True,
                "duplicate_idempotent": True,
                "cross_workspace_denied": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
