"""Real loopback API/Worker/PostgreSQL/MinIO RAG benchmark; owned synthetic fixtures only."""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import DatasetVersion, LicenseGrant, RagChunk, RagIndexVersion
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("CF_API_URL", "http://127.0.0.1:58000/api/v1")


def main():
    fixture = json.loads((ROOT / "tests/fixtures/p1d/corpus.json").read_text())
    unique = uuid4().hex[:12]
    client = httpx.Client(base_url=BASE, timeout=60, trust_env=False)

    def login(name):
        r = client.post(
            "/auth/session",
            json={
                "user_id": f"p1d-{name}-{unique}",
                "display_name": name,
                "workspace_name": f"p1d-{name}-{unique}",
            },
        )
        r.raise_for_status()
        return r.json()

    admin, reviewer, other, viewer = [login(n) for n in ("admin", "reviewer", "other", "viewer")]
    wid = admin["workspace_id"]

    def call(method, path, body=None, who=None, status=200):
        actor = who or admin
        headers = {
            "Authorization": f"Bearer {actor['token']}",
            "X-Workspace-ID": other["workspace_id"] if actor == other else wid,
        }
        r = client.request(method, path, json=body, headers=headers)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    for actor, role in [(reviewer, "reviewer"), (viewer, "viewer")]:
        call("POST", f"/workspaces/{wid}/members", {"user_id": actor["token"], "role": role})
    evidence = {"checks": [], "annotation_status": fixture["annotation_status"], "benchmarks": []}

    def checked(name):
        evidence["checks"].append(name)

    def wait(path, limit=120):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            row = call("GET", path)
            if row["status"] in {"succeeded", "failed"}:
                assert row["status"] == "succeeded", row
                return row
            time.sleep(0.25)
        raise AssertionError(("timeout", path, row))

    source = call("POST", "/sources", {"name": f"original-p1d-{unique}"})
    content = (
        "\n".join(f"<h2>{title}</h2><p>{fact}</p>" for title, fact, _ in fixture["facts"])
    ).encode()
    upload = call(
        "POST",
        "/uploads/init",
        {"filename": "p1d-cryptography.html", "size": len(content), "content_type": "text/html"},
    )
    r = client.put(
        f"/uploads/{upload['upload_id']}/content",
        content=content,
        headers={
            "Authorization": f"Bearer {admin['token']}",
            "X-Workspace-ID": wid,
            "Content-Type": "text/html",
        },
    )
    assert r.status_code == 200, r.text
    call(
        "POST",
        f"/uploads/{upload['upload_id']}/complete",
        {"checksum": hashlib.sha256(content).hexdigest()},
    )
    asset = call(
        "POST",
        "/ingest-batches",
        {"source_id": source["source_id"], "upload_ids": [upload["upload_id"]]},
    )["items"][0]["asset_id"]
    for purpose in ("rag", "evaluation"):
        call(
            "POST",
            "/authorization/grants",
            {
                "asset_id": asset,
                "purpose": purpose,
                "evidence_uri": f"fixture://cc0/{unique}",
                "legal_basis": fixture["license"],
            },
        )
    run = call("POST", "/pipeline-runs/batches", {"asset_ids": [asset], "config": {}})["accepted"][
        0
    ]["run_id"]
    wait(f"/pipeline-runs/{run}")
    detail = call("GET", f"/assets/{asset}")
    segments = detail["versions"][0]["segments"]
    assert len(segments) == 26, len(segments)
    # Evidence comes from exact parser heading and actual Segment, never from filename guesses.
    by_title = {s["section_title"]: s for s in segments}
    selected = [by_title[title] for title, _, _ in fixture["facts"]]

    def product(kind, segs, config, label="1.0.0", dataset=None):
        dataset = (
            dataset
            or call("POST", "/datasets", {"name": f"p1d-{kind}-{unique}", "product_type": kind})[
                "dataset_id"
            ]
        )
        build = call(
            "POST",
            "/dataset-builds",
            {
                "dataset_id": dataset,
                "segment_ids": [s["segment_id"] for s in segs],
                "purpose": "rag" if kind == "rag" else "evaluation",
                "config": config,
            },
        )["build_id"]
        for sample in call("GET", f"/dataset-builds/{build}/candidates")["items"]:
            call(
                "POST",
                f"/candidate-samples/{sample['sample_id']}/reviews",
                {
                    "decision": "approved",
                    "note": "Synthetic fixture assertion review; not expert human annotation",
                },
                who=reviewer,
            )
        assert call("POST", f"/dataset-builds/{build}/validate", {})["ok"]
        release = call(
            "POST", f"/datasets/{dataset}/versions", {"build_id": build, "version": label}
        )
        return dataset, release["dataset_version_id"]

    dataset, vid = product("rag", selected, {"chunk_size": 128, "overlap": 0})
    samples = [
        {
            "question": q,
            "reference_answer": fact,
            "evidence_ids": [by_title[t]["segment_id"]],
            "question_type": "factual",
            "difficulty": "easy",
            "domain": "cryptography",
        }
        for t, fact, q in fixture["facts"]
    ]
    # One separate multi-evidence case, same source document; no copied question padding.
    samples.append(
        {
            "question": "AES SHA-256",
            "reference_answer": "AES block size is 128 bits; SHA-256 digest is 256 bits.",
            "evidence_ids": [by_title["AES"]["segment_id"], by_title["SHA-256"]["segment_id"]],
            "question_type": "multi-evidence",
            "difficulty": "medium",
            "domain": "cryptography",
        }
    )
    _, evid = product("evaluation", selected, {"evaluation_samples": samples})
    suite = call(
        "POST",
        "/rag/suites",
        {
            "dataset_version_id": evid,
            "name": "original-crypto-v1",
            "annotation_note": fixture["annotation_status"],
            "no_answer_queries": fixture["no_answer"],
        },
        who=reviewer,
    )["suite_id"]
    checked("real HTML -> Worker -> 26 segments -> published RAG and Evaluation -> 31 fixed cases")
    key = f"index-{unique}"

    def index_request():
        return call(
            "POST", "/rag/indexes", {"dataset_version_id": vid, "request_key": key}, status=202
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        indexes = list(pool.map(lambda _: index_request(), range(2)))
    iid = indexes[0]["index_version_id"]
    assert indexes[1]["index_version_id"] == iid
    index = wait(f"/rag/indexes/{iid}")
    assert index["chunk_count"] == 26, index
    checked("concurrent duplicate index requests and real async build")
    for task in [celery_app.send_task("corpusflow.rag_job", args=[iid]) for _ in range(2)]:
        assert task.get(timeout=20)["status"] == "succeeded"
    assert call("GET", f"/rag/indexes/{iid}")["chunk_count"] == 26
    checked("actual duplicate Celery deliveries preserve one index and 26 chunks")

    def query(q, mode="bm25", who=None, status=200):
        return call(
            "POST",
            "/rag/queries",
            {"index_version_id": iid, "query": q, "strategy": mode, "top_k": 3},
            who=who,
            status=status,
        )

    first = query("AES block size")
    second = query("Merkle root")
    assert first["hits"][0]["segment_id"] == by_title["AES"]["segment_id"], first
    assert second["hits"][0]["segment_id"] == by_title["Merkle"]["segment_id"], second
    assert first["trace_id"] != second["trace_id"]
    assert not query("quantumunicornplanet")["hits"]
    assert query("AES", "vector", status=409)["error"]["code"] == "ADAPTER_UNAVAILABLE"
    query("AES", who=other, status=404)
    call("GET", f"/rag/traces/{first['trace_id']}", who=other, status=404)
    call(
        "POST",
        "/rag/indexes",
        {"dataset_version_id": vid, "request_key": "viewer-test"},
        who=viewer,
        status=403,
    )
    checked(
        "query snapshots, no evidence, provider unavailable, reader and cross-workspace isolation"
    )
    injection = query("untrusted credentials")
    assert injection["generation"]["answer"] is None
    checked("prompt injection remains inert evidence, no model or tool execution")
    evidence["index"] = index
    evidence["queries"] = [first, second, injection]
    evidence["input_asset_id"] = asset
    evidence["input_sha256"] = hashlib.sha256(content).hexdigest()

    def benchmark(index_id, strategies):
        results = []
        for strategy, rerank in strategies:
            ev = call(
                "POST",
                "/rag/evaluations",
                {
                    "index_version_id": index_id,
                    "suite_id": suite,
                    "request_key": uuid4().hex,
                    "strategy": strategy,
                    "rerank": rerank,
                    "top_k": 3,
                },
                status=202,
            )
            result = wait(f"/rag/evaluations/{ev['evaluation_id']}")
            results.append(result)
        return results

    results = benchmark(iid, [("fts", False), ("bm25", False), ("hybrid", False), ("hybrid", True)])
    assert len({r["report"]["suite_sha256"] for r in results}) == 1
    evidence["benchmarks"] = results
    engine = build_engine(load_settings())
    for table, oid, assignment in [
        ("rag_index_versions", iid, "chunk_count=0"),
        ("retrieval_traces", first["trace_id"], "query='changed'"),
        ("rag_evaluation_suites", suite, "name='changed'"),
        ("rag_evaluation_runs", results[0]["evaluation_id"], "report='{}'::jsonb"),
    ]:
        with Session(engine) as db:
            try:
                with db.begin_nested():
                    db.execute(text(f"UPDATE {table} SET {assignment} WHERE id=:id"), {"id": oid})
            except DBAPIError:
                pass
            else:
                raise AssertionError(f"immutable guard missing: {table}")
    checked("PostgreSQL guards reject updates to completed index, trace, suite and evaluation")

    checked("31 fixed cases: FTS/BM25/RRF/rerank real metrics and latency")
    # Same selected Segment versions, different chunk configuration and published product version.
    _, vid2 = product("rag", selected, {"chunk_size": 12, "overlap": 2}, "2.0.0", dataset)
    ix2 = call(
        "POST", "/rag/indexes", {"dataset_version_id": vid2, "request_key": uuid4().hex}, status=202
    )
    iid2 = ix2["index_version_id"]
    wait(f"/rag/indexes/{iid2}")
    evidence["benchmarks"] += benchmark(iid2, [("bm25", False)])
    checked("same suite across two immutable dataset versions with different chunk configuration")
    # Feedback links query evidence to the established review workflow.
    fb = call(
        "POST",
        "/rag/feedback",
        {
            "trace_id": first["trace_id"],
            "segment_id": by_title["AES"]["segment_id"],
            "category": "chunk",
            "note": "Verify processing lineage and rebuild after explicit reviewed rework",
        },
    )
    call("POST", f"/pipeline-runs/{run}/resume", {}, status=409)
    call(
        "POST",
        f"/quality/issues/{fb['quality_issue_id']}/reviews",
        {"decision": "approved_for_rework", "note": "fixture rework approved"},
        who=reviewer,
    )
    call("POST", f"/pipeline-runs/{run}/resume", {})
    wait(f"/pipeline-runs/{run}")
    issues = call("GET", "/quality/issues")["items"]
    assert (
        next(i for i in issues if i["issue_id"] == fb["quality_issue_id"])["status"] == "resolved"
    )
    detail2 = call("GET", f"/assets/{asset}")
    latest = detail2["versions"][0]["segments"]
    assert {s["segment_id"] for s in latest}.isdisjoint(s["segment_id"] for s in selected)
    _, vid3 = product("rag", latest, {"chunk_size": 128, "overlap": 0}, "3.0.0", dataset)
    ix3 = call(
        "POST", "/rag/indexes", {"dataset_version_id": vid3, "request_key": uuid4().hex}, status=202
    )
    wait(f"/rag/indexes/{ix3['index_version_id']}")
    evidence["benchmarks"] += benchmark(ix3["index_version_id"], [("bm25", False)])
    evidence["feedback"] = {
        **fb,
        "old_asset_version": detail["versions"][0]["document_version_id"],
        "new_dataset_version_id": vid3,
        "new_index_version_id": ix3["index_version_id"],
    }
    checked(
        "feedback -> review -> Worker rework -> new segments/product/index "
        "-> same-suite reevaluation"
    )
    engine = build_engine(load_settings())
    with Session(engine) as db:
        before = index["content_sha256"]
        grant = db.scalar(
            select(LicenseGrant).where(
                LicenseGrant.asset_id == asset, LicenseGrant.purpose == "rag"
            )
        )
        grant_id = grant.id
        grant.status = "revoked"
        db.commit()
        assert (
            db.scalar(select(func.count(RagChunk.id)).where(RagChunk.index_version_id == iid)) == 26
        )
        assert db.get(RagIndexVersion, iid).dataset_version_id == vid
        assert db.get(DatasetVersion, vid).content_sha256 == before
    assert not query("AES")["hits"]
    assert not call("GET", f"/rag/traces/{first['trace_id']}")["hits"]
    denied_index = call(
        "POST", "/rag/indexes", {"dataset_version_id": vid, "request_key": uuid4().hex}, status=202
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        denied = call("GET", f"/rag/indexes/{denied_index['index_version_id']}")
        if denied["status"] == "failed":
            break
        time.sleep(0.25)
    assert denied["error_code"] == "PURPOSE_GRANT_MISSING", denied
    checked("revocation filters fresh and historical results; unauthorized index build fails")
    # Restore only this verifier-owned fixture grant to allow Web validation.
    with Session(engine) as db:
        db.get(LicenseGrant, grant_id).status = "confirmed"
        db.commit()
    out = ROOT / os.environ.get("CF_RAG_EVIDENCE_DIR", ".local/p1d")
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    (out / "web.json").write_text(
        json.dumps(
            {
                "session": admin,
                "index_id": iid,
                "suite_id": suite,
                "dataset_version_id": vid,
                "eval_version_id": evid,
                "reviewer": reviewer,
            },
            ensure_ascii=False,
        )
    )
    print(
        f"P1-D PASS: {len(evidence['checks'])} real checks, 31 cases, "
        f"{len(evidence['benchmarks'])} experiments"
    )


if __name__ == "__main__":
    main()
