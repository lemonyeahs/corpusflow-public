"""Real API, Worker, PostgreSQL vectors and frozen P1-D suite. Uses owned fixture IDs."""

import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import LicenseGrant, RagChunk, RagIndexVersion
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def main():
    # Create a fresh verifier-owned workspace; previous Web feedback may quarantine old assets.
    subprocess.run([sys.executable, "scripts/verify_p1d_rag.py"], check=True)
    fixture = json.loads(Path(".local/p1d/web.json").read_text())
    who = fixture["session"]
    client = httpx.Client(
        base_url="http://127.0.0.1:58000/api/v1",
        timeout=60,
        trust_env=False,
        headers={"Authorization": f"Bearer {who['token']}", "X-Workspace-ID": who["workspace_id"]},
    )

    def call(method, path, body=None, status=200):
        r = client.request(method, path, json=body)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    def wait(path):
        for _ in range(240):
            row = call("GET", path)
            if row["status"] in {"succeeded", "failed"}:
                assert row["status"] == "succeeded", row
                return row
            time.sleep(0.5)
        raise AssertionError((path, row))

    key = uuid4().hex
    body = {
        "dataset_version_id": fixture["dataset_version_id"],
        "request_key": key,
        "embedding": True,
    }
    ix = call("POST", "/rag/indexes", body, 202)
    iid = ix["index_version_id"]
    assert call("POST", "/rag/indexes", body, 202)["index_version_id"] == iid
    index = wait(f"/rag/indexes/{iid}")
    assert index["chunk_count"] == 26
    repeat = call("POST", "/rag/indexes", {**body, "request_key": uuid4().hex}, 202)
    reused = wait(f"/rag/indexes/{repeat['index_version_id']}")
    assert reused["config"]["build_stats"]["vectors_reused"] == 26
    for _ in range(2):
        assert (
            celery_app.send_task("corpusflow.rag_job", args=[iid]).get(timeout=30)["status"]
            == "succeeded"
        )
    benchmarks = []
    for mode, threshold in [
        ("bm25", 0.5),
        ("vector", -1),
        ("vector", 0.5),
        ("semantic_hybrid", 0.5),
    ]:
        run = call(
            "POST",
            "/rag/evaluations",
            {
                "suite_id": fixture["suite_id"],
                "index_version_id": iid,
                "request_key": uuid4().hex,
                "strategy": mode,
                "top_k": 3,
                "min_similarity": threshold,
            },
            202,
        )
        benchmarks.append(wait(f"/rag/evaluations/{run['evaluation_id']}"))
    assert len({r["report"]["suite_sha256"] for r in benchmarks}) == 1
    query = {"index_version_id": iid, "query": "AES block size", "strategy": "vector", "top_k": 3}
    trace = call("POST", "/rag/queries", query)
    assert trace["hits"] and trace["hits"][0]["scores"]["cosine"] > 0.5
    engine = build_engine(load_settings())
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count(RagChunk.id)).where(RagChunk.index_version_id == iid)) == 26
        )
        assert all(
            c.embedding and len(c.embedding) == 384
            for c in db.scalars(select(RagChunk).where(RagChunk.index_version_id == iid))
        )
        assert db.get(RagIndexVersion, iid).config["embedding"]["model_version"]
        try:
            with db.begin_nested():
                db.execute(
                    text("UPDATE rag_chunks SET embedding='[]'::jsonb WHERE index_version_id=:id"),
                    {"id": iid},
                )
        except DBAPIError:
            pass
        else:
            raise AssertionError("Vector immutability guard missing")
        grant = db.scalar(
            select(LicenseGrant).where(
                LicenseGrant.asset_id == trace["hits"][0]["asset_id"], LicenseGrant.purpose == "rag"
            )
        )
        original = grant.status
        grant.status = "revoked"
        db.commit()
        try:
            assert not call("POST", "/rag/queries", query)["hits"]
            assert not call("GET", f"/rag/traces/{trace['trace_id']}")["hits"]
        finally:
            grant.status = original
            db.commit()
    report = {
        "index": index,
        "incremental_reuse": reused,
        "benchmarks": benchmarks,
        "trace": trace,
        "checks": [
            "persistent actual vectors",
            "duplicate messages",
            "incremental content reuse",
            "same frozen suite",
            "immutable vectors",
            "revocation filters fresh and historical hits",
        ],
    }
    Path(".local/p2/semantic-platform.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    Path(".local/p2/semantic-web.json").write_text(
        json.dumps({"index_id": iid, "trace_id": trace["trace_id"]})
    )
    print(
        json.dumps(
            {
                "checks": report["checks"],
                "metrics": [
                    {"strategy": r["report"]["strategy"], "metrics": r["report"]["metrics"]}
                    for r in benchmarks
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
