"""Opted-in original fixture only. Persistent fixed keys prevent repeated billable calls."""

import json
import time
from pathlib import Path

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import GenerationRun
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def main():
    fixture = json.loads(Path(".local/p2/llm-fixture.json").read_text())
    user = fixture["session"]
    client = httpx.Client(
        base_url="http://127.0.0.1:58000/api/v1",
        timeout=30,
        trust_env=False,
        headers={
            "Authorization": f"Bearer {user['token']}",
            "X-Workspace-ID": user["workspace_id"],
        },
    )

    def call(method, path, body=None):
        r = client.request(method, path, json=body)
        assert r.status_code in {200, 202}, (path, r.status_code, r.text)
        return r.json()

    outputs = []
    engine = build_engine(load_settings())
    for question, key in [
        ("AES block size", "p2-original-aes"),
        ("untrusted credentials", "p2-original-injection"),
        ("quantumunicornplanet", "p2-original-no-answer"),
    ]:
        with Session(engine) as db:
            old = db.scalar(
                select(GenerationRun).where(
                    GenerationRun.workspace_id == user["workspace_id"],
                    GenerationRun.request_key == key,
                )
            )
            existing = old.id if old else None
        if existing:
            run = call("GET", f"/rag/answers/{existing}")
        else:
            trace = call(
                "POST",
                "/rag/queries",
                {"index_version_id": fixture["index_id"], "query": question, "top_k": 3},
            )
            run = call("POST", "/rag/answers", {"trace_id": trace["trace_id"], "request_key": key})
        for _ in range(150):
            if run["status"] in {"succeeded", "failed", "refused"}:
                break
            time.sleep(0.5)
            run = call("GET", f"/rag/answers/{run['generation_id']}")
        assert run["status"] in {"succeeded", "failed", "refused"}, run
        outputs.append(run)
    # Duplicate delivery must never consume a second reservation or provider call.
    with Session(engine) as db:
        before = db.scalar(
            select(func.count(GenerationRun.id)).where(GenerationRun.call_reserved.is_(True))
        )
    for row in outputs:
        celery_app.send_task("corpusflow.generate", args=[row["generation_id"]]).get(timeout=20)
    with Session(engine) as db:
        after = db.scalar(
            select(func.count(GenerationRun.id)).where(GenerationRun.call_reserved.is_(True))
        )
    assert before == after and after <= 10
    assert outputs[-1]["status"] == "refused" and not outputs[-1]["call_reserved"]
    Path(".local/p2/generation-evidence.json").write_text(
        json.dumps(
            {
                "results": outputs,
                "reserved_calls": after,
                "max_calls": 10,
                "max_output_tokens": 512,
                "dataset": "self-authored CC0 P1-D fixture only",
                "checks": [
                    "duplicate message no extra reservation",
                    "no evidence no provider call",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "statuses": [(r["status"], r["error_code"]) for r in outputs],
                "reserved_calls": after,
                "usage": [r["result"].get("usage") for r in outputs],
            }
        )
    )
    if outputs[0]["status"] != "succeeded":
        raise SystemExit(
            "GENERATION ACCEPTANCE FAIL: no successful evidence answer; see safe error codes"
        )


if __name__ == "__main__":
    main()
