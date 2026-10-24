"""Verify concurrent publication creates one immutable DatasetVersion."""

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from corpusflow.core.config import load_settings
from corpusflow.db.models import DatasetVersion, Membership, Segment, User
from corpusflow.db.session import build_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BASE = "http://127.0.0.1:58000/api/v1"


def call(method: str, path: str, token: str, workspace: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": workspace,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> None:
    settings = load_settings()
    factory = sessionmaker(build_engine(settings), expire_on_commit=False)
    with factory() as session:
        admin = session.scalar(
            select(User).where(User.oidc_sub.like("acceptance-admin-%")).order_by(User.created_at.desc())
        )
        memberships = session.scalars(
            select(Membership).where(Membership.user_id == admin.id, Membership.role == "admin")
        ).all()
        workspace_ids = [membership.workspace_id for membership in memberships]
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
        ) if latest else None
        assert admin and reviewer and latest and segment
        workspace = latest.workspace_id
    admin_token, reviewer_token = admin.oidc_sub, reviewer.oidc_sub

    status, dataset = call(
        "POST", "/datasets", admin_token, workspace, {"name": f"p0i-concurrent-{uuid4().hex[:8]}"}
    )
    assert status == 200, dataset
    status, build = call(
        "POST",
        "/dataset-builds",
        admin_token,
        workspace,
        {"dataset_id": dataset["dataset_id"], "segment_ids": [segment.id], "purpose": "training"},
    )
    assert status == 200
    candidates = call(
        "GET", f"/dataset-builds/{build['build_id']}/candidates", admin_token, workspace
    )[1]
    sample_id = candidates["items"][0]["sample_id"]
    assert call(
        "POST",
        f"/candidate-samples/{sample_id}/reviews",
        reviewer_token,
        workspace,
        {"decision": "approved", "note": "concurrency test"},
    )[0] == 200
    assert call(
        "POST", f"/dataset-builds/{build['build_id']}/validate", admin_token, workspace, {}
    )[1]["ok"]

    version_label = f"8.8.{datetime.now(UTC).microsecond % 100000}"

    def publish():
        return call(
            "POST",
            f"/datasets/{dataset['dataset_id']}/versions",
            admin_token,
            workspace,
            {"build_id": build["build_id"], "version": version_label},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publish(), range(2)))
    statuses = sorted(result[0] for result in results)
    # The advisory lock may let the second request observe the committed
    # version and return an idempotent 200, or it may race before the lock and
    # receive the conflict response. Both outcomes preserve one version.
    assert statuses in ([200, 200], [200, 409]), results
    with factory() as session:
        versions = session.scalars(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset["dataset_id"],
                DatasetVersion.version == version_label,
            )
        ).all()
        assert len(versions) == 1
    print("PUBLISH_CONCURRENCY PASS")
    print(json.dumps({"statuses": statuses, "visible_versions": 1}))


if __name__ == "__main__":
    main()
