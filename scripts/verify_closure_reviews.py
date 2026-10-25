"""Actual blind-review workflow over saved original-fixture answers; zero provider calls."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import ReviewTask
from corpusflow.db.session import build_engine
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def main():
    fixture = json.loads(Path(".local/p2/llm-fixture.json").read_text())
    answers = json.loads(Path(".local/p2/generation-evidence.json").read_text())["results"][:2]
    admin = fixture["session"]
    first = fixture["reviewer"]
    wid = admin["workspace_id"]
    with httpx.Client(
        base_url="http://127.0.0.1:58000/api/v1", trust_env=False, timeout=20
    ) as client:

        def call(method, path, body=None, who=admin, workspace=wid, status=200):
            r = client.request(
                method,
                path,
                json=body,
                headers={"Authorization": f"Bearer {who['token']}", "X-Workspace-ID": workspace},
            )
            assert r.status_code == status, (path, r.status_code, r.text)
            return r.json()

        second = call(
            "POST",
            "/auth/session",
            {
                "user_id": "blind-" + uuid4().hex,
                "display_name": "Synthetic workflow rater",
                "workspace_name": "Own test workspace",
            },
        )
        call("POST", f"/workspaces/{wid}/members", {"user_id": second["token"], "role": "reviewer"})
        body = {
            "request_key": uuid4().hex,
            "cases": [
                {"trace_id": r["trace_id"], "generation_id": r["generation_id"]} for r in answers
            ],
            "reviewer_ids": [first["user_id"], second["user_id"]],
        }
        task = call("POST", "/review-tasks", body)
        assert call("POST", "/review-tasks", body) == task
        call(
            "POST",
            "/review-tasks",
            {**body, "reviewer_ids": [first["user_id"], admin["user_id"]]},
            status=409,
        )
        export = call("GET", f"/review-tasks/{task['task_id']}/export")
        assignments = {a["reviewer_id"]: a["assignment_id"] for a in export["assignments"]}
        aid = assignments[first["user_id"]]
        view = call("GET", f"/review-tasks/assignments/{aid}", who=first)
        for c in view["cases"]:
            assert "trace_id" not in c and "generation_id" not in c and "config" not in c
            assert all("scores" not in h for h in c["evidence"])
        call("GET", f"/review-tasks/assignments/{aid}", who=second, status=404)
        call(
            "GET",
            f"/review-tasks/assignments/{aid}",
            who=second,
            workspace=second["workspace_id"],
            status=404,
        )
        call("GET", f"/review-tasks/{task['task_id']}/export", who=first, status=403)
        score = {
            "evidence_support": 3,
            "completeness": 3,
            "answer_correctness": 3,
            "irrelevant": False,
            "unsupported_answer": False,
            "no_answer_expected": False,
            "note": "Synthetic rubric workflow check; not expert judgment",
        }
        payload = {"scores": [score, {**score, "no_answer_expected": True}]}
        target = f"/review-tasks/assignments/{assignments[second['user_id']]}/scores"
        call("POST", target, payload, who=second)
        call("POST", target, payload, who=second)
        call(
            "POST",
            target,
            {"scores": [{**score, "evidence_support": 0}, score]},
            who=second,
            status=409,
        )
        submitted = call(
            "GET", f"/review-tasks/assignments/{assignments[second['user_id']]}", who=second
        )
        assert len(submitted["own_scores"]) == 2
        assert all("generation_id" not in item for item in submitted["own_scores"])
        engine = build_engine(load_settings())
        with Session(engine) as db:
            try:
                db.execute(
                    update(ReviewTask).where(ReviewTask.id == task["task_id"]).values(snapshot={})
                )
            except DBAPIError:
                pass
            else:
                raise AssertionError("Frozen task was mutable")
            finally:
                db.rollback()
        engine.dispose()
        Path(".local/closure/review-web.json").write_text(
            json.dumps(
                {
                    "session": {**first, "workspace_id": wid, "role": "reviewer"},
                    "admin": admin,
                    "assignment_id": aid,
                    "task_id": task["task_id"],
                    "snapshot_sha256": task["snapshot_sha256"],
                }
            )
        )
        Path(".local/closure/review-api.json").write_text(
            json.dumps(
                {
                    "task": task,
                    "checks": [
                        "assignment isolation",
                        "workspace isolation",
                        "reviewer export denied",
                        "frozen snapshot",
                        "hidden model/strategy/peer scores",
                        "submission idempotency",
                        "conflicting overwrite denied",
                    ],
                    "new_model_calls": 0,
                    "expert_participation": "NOT_RUN",
                },
                indent=2,
            )
            + "\n"
        )
    print(
        "PASS: actual blind assignment, permissions, frozen versions; expert participation NOT_RUN"
    )


if __name__ == "__main__":
    main()
