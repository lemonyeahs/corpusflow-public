"""Real API review workflow; synthetic tester scores, NOT expert evaluation."""

import json
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    fixture = json.loads(Path(".local/p1d/web.json").read_text())
    trace = json.loads(Path(".local/p2/semantic-web.json").read_text())["trace_id"]
    admin, reviewer = fixture["session"], fixture["reviewer"]
    wid = admin["workspace_id"]
    client = httpx.Client(base_url="http://127.0.0.1:58000/api/v1", timeout=30, trust_env=False)

    def call(method, path, body=None, who=admin, workspace=wid, status=200):
        r = client.request(
            method,
            path,
            json=body,
            headers={"Authorization": f"Bearer {who['token']}", "X-Workspace-ID": workspace},
        )
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    engineer = call(
        "POST",
        "/auth/session",
        {
            "user_id": "review-test-" + uuid4().hex,
            "display_name": "Fixture engineer",
            "workspace_name": "Own isolated workspace",
        },
    )
    call("POST", f"/workspaces/{wid}/members", {"user_id": engineer["token"], "role": "engineer"})
    body = {
        "trace_id": trace,
        "request_key": uuid4().hex,
        "evidence_support": 4,
        "completeness": 3,
        "irrelevant": False,
        "no_answer_expected": False,
        "note": "Synthetic workflow assertion; not expert opinion",
    }
    first = call("POST", "/rag/reviews", body, who=reviewer)
    assert call("POST", "/rag/reviews", body, who=reviewer) == first
    call("POST", "/rag/reviews", {**body, "completeness": 0}, who=reviewer, status=409)
    call("POST", "/rag/reviews", {**body, "request_key": uuid4().hex}, who=engineer, status=403)
    call("POST", "/rag/reviews", {**body, "request_key": uuid4().hex, "evidence_support": 1})
    report = call("GET", f"/rag/traces/{trace}/reviews")
    assert report["reviewer_count"] == 2 and report["disagreement"] == 3
    call(
        "GET",
        f"/rag/traces/{trace}/reviews",
        who=engineer,
        workspace=engineer["workspace_id"],
        status=404,
    )
    Path(".local/p2/review-evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print("PASS: real reviews, idempotency, disagreement and authorization; expert scores NOT_RUN")


if __name__ == "__main__":
    main()
