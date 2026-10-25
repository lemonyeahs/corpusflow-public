"""Real review/outbox/Worker denial path. Successful external acquisition is a separate gate."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import Asset, LicenseGrant
from corpusflow.db.session import build_engine
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def main():
    client = httpx.Client(base_url="http://127.0.0.1:58000/api/v1", timeout=30, trust_env=False)

    def login(name):
        return client.post(
            "/auth/session",
            json={"user_id": name + uuid4().hex, "display_name": name, "workspace_name": name},
        ).json()

    admin, reviewer = login("collection-fixture"), login("collection-reviewer")
    wid = admin["workspace_id"]

    def call(method, path, body=None, who=admin, status=200, workspace=wid):
        r = client.request(
            method,
            path,
            json=body,
            headers={"Authorization": f"Bearer {who['token']}", "X-Workspace-ID": workspace},
        )
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    call("POST", f"/workspaces/{wid}/members", {"user_id": reviewer["token"], "role": "reviewer"})
    source = call(
        "POST", "/sources", {"name": "Public bibliographic metadata network boundary test"}
    )["source_id"]
    candidate = call(
        "POST",
        "/discovery-candidates",
        {
            "title": "Crossref metadata only; not document license",
            "url": "https://api.crossref.org/works/10.1038/s41586-020-2649-2",
        },
    )["candidate_id"]
    body = {"source_id": source, "candidate_ids": [candidate], "request_key": uuid4().hex}
    plan = call("POST", "/collection/plans", body)
    pid = plan["plan_id"]
    assert call("POST", "/collection/plans", body)["plan_id"] == pid
    review = {
        "approve": True,
        "legal_basis": "Public Crossref metadata only; no abstract, fulltext or purpose grant",
    }
    call("POST", f"/collection/plans/{pid}/review", review, status=409)
    call("POST", f"/collection/plans/{pid}/review", review, who=reviewer, status=202)
    call(
        "GET",
        f"/collection/plans/{pid}",
        who=reviewer,
        workspace=reviewer["workspace_id"],
        status=404,
    )
    for _ in range(60):
        state = call("GET", f"/collection/plans/{pid}")
        if state["status"] == "failed":
            break
        time.sleep(0.5)
    assert state["status"] == "failed" and state["error_code"] in {
        "ACQUISITION_ADDRESS_REJECTED",
        "ACQUISITION_FORMAT_REJECTED",
    }, state
    assert state["results"] == []
    rejected = call("POST", "/collection/plans", {**body, "request_key": uuid4().hex})["plan_id"]
    call(
        "POST",
        f"/collection/plans/{rejected}/review",
        {**review, "approve": False},
        who=reviewer,
        status=202,
    )
    call("POST", f"/collection/plans/{rejected}/review", review, who=reviewer, status=409)
    with Session(build_engine(load_settings())) as db:
        assert db.scalar(select(func.count(Asset.id)).where(Asset.workspace_id == wid)) == 0
        assert (
            db.scalar(select(func.count(LicenseGrant.id)).where(LicenseGrant.workspace_id == wid))
            == 0
        )
    Path(".local/p2/collection-evidence.json").write_text(
        json.dumps(
            {
                "plan": state,
                "checks": [
                    "separation of duties",
                    "idempotency",
                    "workspace isolation",
                    "actual outbox and Worker denial",
                    "no asset or purpose grant",
                    "rejected plan cannot reopen",
                ],
                "external_success": "NOT_RUN: local DNS maps public hosts to non-global 198.18.0.x",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    Path(".local/p2/collection-web.json").write_text(json.dumps({"session": admin, "plan_id": pid}))
    print("PASS: actual plan/review/Worker fail-closed flow. External acquisition success BLOCKED.")


if __name__ == "__main__":
    main()
