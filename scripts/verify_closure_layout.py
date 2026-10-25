"""Actual geometric PDF -> MinIO -> Celery layout parser -> located segments."""

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import AssetBlob, Document, DocumentVersion, PipelineRun
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def main():
    client = httpx.Client(base_url="http://127.0.0.1:58000/api/v1", timeout=30, trust_env=False)
    user = client.post(
        "/auth/session",
        json={
            "user_id": "layout-" + uuid4().hex,
            "display_name": "Layout fixture",
            "workspace_name": "Closure layout fixture",
        },
    ).json()
    client.headers.update(
        {"Authorization": f"Bearer {user['token']}", "X-Workspace-ID": user["workspace_id"]}
    )

    def call(method, path, body=None, status=200):
        r = client.request(method, path, json=body)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    source = call("POST", "/sources", {"name": "Original CC0 multi-column fixture"})["source_id"]
    content = Path("tests/fixtures/closure/columns.pdf").read_bytes()
    upload = call(
        "POST",
        "/uploads/init",
        {"filename": "columns.pdf", "size": len(content), "content_type": "application/pdf"},
    )["upload_id"]
    assert (
        client.put(
            f"/uploads/{upload}/content",
            content=content,
            headers={"Content-Type": "application/pdf"},
        ).status_code
        == 200
    )
    call("POST", f"/uploads/{upload}/complete", {"checksum": hashlib.sha256(content).hexdigest()})
    asset = call("POST", "/ingest-batches", {"source_id": source, "upload_ids": [upload]})["items"][
        0
    ]["asset_id"]

    def run(config):
        run_id = call("POST", "/pipeline-runs/batches", {"asset_ids": [asset], "config": config})[
            "accepted"
        ][0]["run_id"]
        for _ in range(120):
            result = call("GET", f"/pipeline-runs/{run_id}")
            if result["status"] in {"succeeded", "failed"}:
                return result
            time.sleep(0.5)
        raise AssertionError(result)

    result = run({"parser": "layout"})
    assert result["status"] == "succeeded", result
    detail = call("GET", f"/assets/{asset}")
    versions = detail["versions"]
    texts = [s["text"] for v in versions for s in v["segments"]]
    assert any("LEFT-ONE AES" in t for t in texts), texts
    assert any(s["location"].get("bbox") for v in versions for s in v["segments"])
    run_id = result["run_id"]
    engine = build_engine(load_settings())
    with Session(engine) as db:
        assert db.get(PipelineRun, run_id).config_snapshot["parser"] == "layout"
        count = db.scalar(
            select(func.count(DocumentVersion.id)).join(Document).where(Document.asset_id == asset)
        )
        assert db.scalar(
            select(AssetBlob.byte_size).where(
                AssetBlob.sha256 == hashlib.sha256(content).hexdigest()
            )
        ) == len(content)
    duplicate = celery_app.send_task("corpusflow.execute_pipeline_run", args=[run_id]).get(
        timeout=30
    )
    assert duplicate["status"] == "succeeded"
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count(DocumentVersion.id))
                .join(Document)
                .where(Document.asset_id == asset)
            )
            == count
        )
    Path(".local/closure/layout-platform.json").write_text(
        json.dumps(
            {
                "input_sha256": hashlib.sha256(content).hexdigest(),
                "layout": result,
                "asset": detail,
                "checks": [
                    "real multi-column upload",
                    "Docker layout actual text",
                    "frozen parser config",
                    "duplicate delivery no new versions",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    Path(".local/closure/layout-web.json").write_text(
        json.dumps({"session": user, "asset_id": asset, "run_id": run_id})
    )
    print("PASS: actual Docker layout, text, locations and duplicate-message assertions")


if __name__ == "__main__":
    main()
