"""Same frozen suite, actual local bi-encoder inference; no external LLM calls."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    fixture = json.loads(Path(".local/p1d/web.json").read_text())
    index = json.loads(Path(".local/p2/semantic-web.json").read_text())["index_id"]
    who = fixture["session"]
    client = httpx.Client(
        base_url="http://127.0.0.1:58000/api/v1",
        trust_env=False,
        timeout=30,
        headers={"Authorization": f"Bearer {who['token']}", "X-Workspace-ID": who["workspace_id"]},
    )
    results = []
    for strategy, rerank, k in [
        ("bm25", False, 3),
        ("bm25", True, 3),
        ("semantic_hybrid", True, 3),
        ("semantic_hybrid", True, 5),
    ]:
        r = client.post(
            "/rag/evaluations",
            json={
                "suite_id": fixture["suite_id"],
                "index_version_id": index,
                "request_key": uuid4().hex,
                "strategy": strategy,
                "semantic_rerank": rerank,
                "top_k": k,
            },
        )
        assert r.status_code == 202, r.text
        oid = r.json()["evaluation_id"]
        for _ in range(240):
            result = client.get(f"/rag/evaluations/{oid}").json()
            if result["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.25)
        assert result["status"] == "succeeded", result
        results.append(result)
    assert len({r["report"]["suite_sha256"] for r in results}) == 1
    report = {
        "kind": "local MiniLM bi-encoder cosine reranker, NOT cross-encoder",
        "benchmarks": results,
    }
    Path(".local/p2/reranker-evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            [
                {"config": r["report"]["strategy"], "metrics": r["report"]["metrics"]}
                for r in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
