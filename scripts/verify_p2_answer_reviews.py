"""Verify reviews and DB guards against existing original-fixture answers; zero model calls."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import GenerationRun
from corpusflow.db.session import build_engine
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def main():
    fixture = json.loads(Path(".local/p2/llm-fixture.json").read_text())
    answer = json.loads(Path(".local/p2/generation-evidence.json").read_text())["results"][0]
    assert answer["status"] == "succeeded"
    admin, reviewer = fixture["session"], fixture["reviewer"]
    with httpx.Client(
        base_url="http://127.0.0.1:58000/api/v1", trust_env=False, timeout=15
    ) as client:

        def call(
            method, path, body=None, who=reviewer, workspace=admin["workspace_id"], status=200
        ):
            response = client.request(
                method,
                path,
                json=body,
                headers={
                    "Authorization": f"Bearer {who['token']}",
                    "X-Workspace-ID": workspace,
                },
            )
            assert response.status_code == status, (path, response.status_code)
            return response.json()

        body = {
            "trace_id": answer["trace_id"],
            "generation_id": answer["generation_id"],
            "request_key": uuid4().hex,
            "answer_correctness": 4,
            "unsupported_answer": False,
            "evidence_support": 4,
            "completeness": 4,
            "irrelevant": False,
            "no_answer_expected": False,
            "note": "Fixture workflow check, NOT expert judgment",
        }
        first = call("POST", "/rag/reviews", body)
        assert call("POST", "/rag/reviews", body) == first
        call("POST", "/rag/reviews", {**body, "answer_correctness": 1}, status=409)
        call(
            "POST",
            "/rag/reviews",
            {**body, "request_key": uuid4().hex, "generation_id": str(uuid4())},
            status=404,
        )
        report = call("GET", f"/rag/traces/{answer['trace_id']}/reviews")
        assert any(
            row["generation_id"] == answer["generation_id"] for row in report["answer_reviews"]
        )
    # Tests alter only this verifier-owned record inside transactions that must fail/rollback.
    engine = build_engine(load_settings())
    operations = [
        update(GenerationRun).values(result={"tampered": True}),
        update(GenerationRun).values(call_reserved=False),
        delete(GenerationRun),
    ]
    with Session(engine) as db:
        for operation in operations:
            try:
                db.execute(operation.where(GenerationRun.id == answer["generation_id"]))
            except DBAPIError as exc:
                assert "generation reservation and result are immutable" in str(exc.orig)
            else:
                raise AssertionError("Immutable generation guard did not reject mutation")
            finally:
                db.rollback()
    engine.dispose()
    Path(".local/p2/answer-review-evidence.json").write_text(
        json.dumps(
            {
                "generation_id": answer["generation_id"],
                "report": report,
                "checks": [
                    "review idempotency",
                    "conflicting score denied",
                    "unknown answer denied",
                    "terminal answer update denied",
                    "budget reservation reset denied",
                    "deletion denied",
                ],
                "provider_calls": 0,
                "expert_participation": "NOT_RUN",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print("PASS: answer review and immutable budget/result guards; zero provider calls")


if __name__ == "__main__":
    main()
