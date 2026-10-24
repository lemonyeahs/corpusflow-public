"""Run the disposable P0-B..P0-F API acceptance flow against local PostgreSQL.

The script uses a unique workspace and synthetic bytes. It never drops a
database or touches production endpoints.
"""

import time
from uuid import uuid4

from corpusflow.core.config import load_settings
from corpusflow.db.models import Segment
from corpusflow.db.session import build_engine
from corpusflow.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def call(response, status=200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json()


def main() -> None:
    suffix = uuid4().hex[:10]
    admin_token = f"acceptance-admin-{suffix}"
    reviewer_token = f"acceptance-reviewer-{suffix}"
    with TestClient(create_app(load_settings())) as client:
        admin = call(
            client.post(
                "/api/v1/auth/session",
                json={
                    "user_id": admin_token,
                    "display_name": "Acceptance Admin",
                    "workspace_name": "Acceptance Business Loop",
                },
            )
        )
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "X-Workspace-ID": admin["workspace_id"],
        }
        reviewer = call(
            client.post(
                "/api/v1/auth/session",
                json={
                    "user_id": reviewer_token,
                    "display_name": "Acceptance Reviewer",
                    "workspace_name": "Acceptance Reviewer Space",
                },
            )
        )
        call(
            client.post(
                f"/api/v1/workspaces/{admin['workspace_id']}/members",
                headers=headers,
                json={"user_id": reviewer["token"], "role": "reviewer"},
            )
        )
        reviewer_headers = {
            "Authorization": f"Bearer {reviewer_token}",
            "X-Workspace-ID": admin["workspace_id"],
        }
        source = call(client.post("/api/v1/sources", headers=headers, json={"name": "acceptance"}))
        source_id = source["source_id"]

        partial_uploads = []
        for name, content in (("failed.md", b"failed"), ("ok-1.md", b"one"), ("ok-2.md", b"two")):
            upload = call(
                client.post(
                    "/api/v1/uploads/init",
                    headers=headers,
                    json={"filename": name, "size": len(content), "content_type": "text/markdown"},
                )
            )
            partial_uploads.append((upload["upload_id"], content))
        for upload_id, content in partial_uploads[1:]:
            call(client.post(f"/api/v1/uploads/{upload_id}/content", headers=headers, data=content))
            call(client.post(f"/api/v1/uploads/{upload_id}/complete", headers=headers, json={}))
        partial = call(
            client.post(
                "/api/v1/ingest-batches",
                headers=headers,
                json={"upload_ids": [item[0] for item in partial_uploads], "source_id": source_id},
            )
        )
        assert partial["totals"] == {"total": 3, "succeeded": 2, "failed": 1}

        assets = []
        for index, content in enumerate(
            (
                b"<h1>alpha</h1><p>alpha evidence</p>",
                b"<h1>beta</h1><p>beta evidence</p>",
                b"<h1>gamma</h1><p>gamma evidence</p>",
            )
        ):
            upload = call(
                client.post(
                    "/api/v1/uploads/init",
                    headers=headers,
                    json={
                        "filename": f"asset-{index}.html",
                        "size": len(content),
                        "content_type": "text/html",
                    },
                )
            )
            upload_id = upload["upload_id"]
            call(client.post(f"/api/v1/uploads/{upload_id}/content", headers=headers, data=content))
            call(client.post(f"/api/v1/uploads/{upload_id}/complete", headers=headers, json={}))
            batch = call(
                client.post(
                    "/api/v1/ingest-batches",
                    headers=headers,
                    json={"upload_ids": [upload_id], "source_id": source_id},
                )
            )
            asset_id = batch["items"][0]["asset_id"]
            assets.append(asset_id)
            call(
                client.post(
                    "/api/v1/authorization/grants",
                    headers=headers,
                    json={
                        "asset_id": asset_id,
                        "purpose": "training",
                        "evidence_uri": "https://example.invalid/license",
                        "legal_basis": "synthetic acceptance fixture",
                    },
                )
            )

        runs = call(
            client.post(
                "/api/v1/pipeline-runs/batches",
                headers=headers,
                json={"asset_ids": assets, "config": {"parser": "builtin"}},
            )
        )
        assert len(runs["accepted"]) == 3
        run_ids, segment_ids = [], []
        for accepted in runs["accepted"]:
            call(
                client.post(f"/api/v1/pipeline-runs/{accepted['run_id']}/execute", headers=headers),
                202,
            )
            run_ids.append(accepted["run_id"])
        for _ in range(20):
            statuses = [
                call(client.get(f"/api/v1/pipeline-runs/{rid}", headers=headers))["status"]
                for rid in run_ids
            ]
            if all(status == "succeeded" for status in statuses):
                break
            time.sleep(0.5)
        assert all(status == "succeeded" for status in statuses), statuses
        factory = sessionmaker(build_engine(load_settings()), expire_on_commit=False)
        with factory() as db:
            segment_ids = list(
                db.scalars(
                    select(Segment.id).where(Segment.workspace_id == admin["workspace_id"])
                ).all()
            )[-3:]
        issue = call(
            client.post(
                "/api/v1/quality/issues",
                headers=headers,
                json={"run_id": run_ids[0], "asset_id": assets[0], "reason": "acceptance issue"},
            )
        )
        blocked = call(
            client.post(f"/api/v1/pipeline-runs/{run_ids[0]}/resume", headers=headers), 409
        )
        assert blocked["error"]["code"] == "RUN_REVIEW_BLOCKED"
        call(
            client.post(
                f"/api/v1/quality/issues/{issue['issue_id']}/reviews",
                headers=reviewer_headers,
                json={"decision": "approved_for_rework"},
            )
        )
        assert (
            call(client.post(f"/api/v1/pipeline-runs/{run_ids[0]}/resume", headers=headers))[
                "status"
            ]
            == "queued"
        )
        call(client.post(f"/api/v1/pipeline-runs/{run_ids[0]}/execute", headers=headers), 202)

        for _ in range(60):
            run_state = call(client.get(f"/api/v1/pipeline-runs/{run_ids[0]}", headers=headers))[
                "status"
            ]
            issue_rows = call(client.get("/api/v1/quality/issues", headers=headers))["items"]
            issue_state = next(
                row["status"] for row in issue_rows if row["issue_id"] == issue["issue_id"]
            )
            if run_state == "succeeded" and issue_state == "resolved":
                break
            time.sleep(0.3)
        assert run_state == "succeeded" and issue_state == "resolved", (run_state, issue_state)

        dataset = call(
            client.post("/api/v1/datasets", headers=headers, json={"name": "acceptance-sft"})
        )
        preview = call(
            client.post(
                "/api/v1/dataset-builds/preview",
                headers=headers,
                json={"purpose": "training", "segment_ids": segment_ids},
            )
        )
        assert preview["included_count"] == 3
        build = call(
            client.post(
                "/api/v1/dataset-builds",
                headers=headers,
                json={
                    "dataset_id": dataset["dataset_id"],
                    "segment_ids": segment_ids,
                    "purpose": "training",
                    "config": {"split": "source_group"},
                },
            )
        )
        candidates = call(
            client.get(f"/api/v1/dataset-builds/{build['build_id']}/candidates", headers=headers)
        )["items"]
        for candidate in candidates:
            call(
                client.post(
                    f"/api/v1/candidate-samples/{candidate['sample_id']}/reviews",
                    headers=reviewer_headers,
                    json={"decision": "approved"},
                )
            )
        assert call(
            client.post(f"/api/v1/dataset-builds/{build['build_id']}/validate", headers=headers)
        )["ok"]
        version = call(
            client.post(
                f"/api/v1/datasets/{dataset['dataset_id']}/versions",
                headers=headers,
                json={"build_id": build["build_id"], "version": "1.0.0"},
            )
        )
        assert version["status"] == "published"
        lineage = call(
            client.get(
                f"/api/v1/lineage/CandidateSample/{candidates[0]['sample_id']}", headers=headers
            )
        )
        assert lineage["edges"]
        print("P0-C PASS: partial ingest and asset registration")
        print("P0-D PASS: N=3 runs, review block, explicit resume and re-run")
        print("P0-E PASS: preview, candidate review, validation and immutable publish")
        print("P0-F PASS: workspace-scoped lineage and audit-backed API")


if __name__ == "__main__":
    main()
