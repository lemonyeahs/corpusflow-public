"""Self-contained P1-C acceptance against loopback Docker API, Worker, PG and MinIO.

Creates uniquely named synthetic fixtures; never modifies existing published data.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from corpusflow.core.config import load_settings
from corpusflow.db.models import Asset, DatasetQualityReport, DatasetVersion, LicenseGrant
from corpusflow.db.session import build_engine
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:58000/api/v1"


def main() -> None:
    unique = uuid4().hex[:12]
    client = httpx.Client(base_url=BASE, timeout=40, trust_env=False)

    def login(name):
        response = client.post(
            "/auth/session",
            json={
                "user_id": f"p1c-{name}-{unique}",
                "display_name": name,
                "workspace_name": f"p1c-{name}-{unique}",
            },
        )
        response.raise_for_status()
        return response.json()

    admin, reviewer, other = login("admin"), login("reviewer"), login("other")
    wid = admin["workspace_id"]
    headers = {"Authorization": f"Bearer {admin['token']}", "X-Workspace-ID": wid}

    def call(method, path, body=None, who=None, status=200):
        actor = who or admin
        response = client.request(
            method,
            path,
            headers={
                "Authorization": f"Bearer {actor['token']}",
                "X-Workspace-ID": wid if actor != other else other["workspace_id"],
            },
            json=body,
        )
        assert response.status_code == status, (path, response.status_code, response.text)
        return response.json()

    call("POST", f"/workspaces/{wid}/members", {"user_id": reviewer["token"], "role": "reviewer"})
    evidence: dict = {
        "checks": [],
        "workspace_id": wid,
        "products": {},
        "sample_origin": "original synthetic HTML; real parser and Worker",
    }

    def checked(name):
        evidence["checks"].append(name)

    engine = build_engine(load_settings())

    def ingest(name, paragraphs, purpose):
        source = call("POST", "/sources", {"name": f"p1c-{name}-{unique}", "kind": "upload"})
        content = (
            "<html><body><h1>"
            + name
            + "</h1>"
            + "".join(f"<p>{value}</p>" for value in paragraphs)
            + "</body></html>"
        ).encode()
        upload = call(
            "POST",
            "/uploads/init",
            {"filename": name + ".html", "size": len(content), "content_type": "text/html"},
        )
        response = client.put(
            f"/uploads/{upload['upload_id']}/content",
            headers={**headers, "Content-Type": "text/html"},
            content=content,
        )
        assert response.status_code == 200, response.text
        call(
            "POST",
            f"/uploads/{upload['upload_id']}/complete",
            {"checksum": hashlib.sha256(content).hexdigest()},
        )
        item = call(
            "POST",
            "/ingest-batches",
            {"upload_ids": [upload["upload_id"]], "source_id": source["source_id"]},
        )["items"][0]
        asset_id = item["asset_id"]
        run_id = call(
            "POST", "/pipeline-runs/batches", {"asset_ids": [asset_id], "config": {}}, status=200
        )["accepted"][0]["run_id"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            run = call("GET", f"/pipeline-runs/{run_id}")
            if run["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.3)
        assert run["status"] == "succeeded", run
        call(
            "POST",
            "/authorization/grants",
            {
                "asset_id": asset_id,
                "purpose": purpose,
                "evidence_uri": f"fixture://owned/{unique}/{name}",
                "legal_basis": "original synthetic fixture",
            },
        )
        detail = call("GET", f"/assets/{asset_id}")
        segments = detail["versions"][-1]["segments"]
        with Session(engine) as db:
            asset = db.get(Asset, asset_id)
            asset.metadata_json = {
                "domains": ["cryptography/hash", "cryptography/signature", "cryptography/hash"]
            }
            db.commit()
        return asset_id, segments

    train_asset, train = ingest(
        "training",
        [
            "Hash functions map arbitrary length inputs into fixed length outputs.",
            "Digital signatures bind a message to a verified public key.",
        ],
        "training",
    )
    rag_asset, rag = ingest(
        "knowledge",
        [
            "A knowledge chunk retains the source page and heading for original evidence.",
            "Chunk overlap retains adjacent context during document splitting.",
        ],
        "rag",
    )
    eval_asset, evaluation = ingest(
        "assessment",
        [
            "The independent assessment fixture explains that a nonce must be unique.",
            "A reference answer is reviewed against this original evidence.",
        ],
        "evaluation",
    )
    checked("three real HTML assets parsed by Worker")

    def build_product(product, segments, config=None, dataset_id=None):
        dataset_id = (
            dataset_id
            or call(
                "POST", "/datasets", {"name": f"p1c-{product}-{unique}", "product_type": product}
            )["dataset_id"]
        )
        cfg = config or {}
        if product == "evaluation":
            cfg = {
                **cfg,
                "evaluation_samples": [
                    {
                        "question": "What must be unique?",
                        "reference_answer": "A nonce must be unique.",
                        "evidence_ids": [segments[0]["segment_id"]],
                        "question_type": "open",
                        "difficulty": "easy",
                        "domain": "cryptography",
                    }
                ],
            }
        build = call(
            "POST",
            "/dataset-builds",
            {
                "dataset_id": dataset_id,
                "segment_ids": [seg["segment_id"] for seg in segments],
                "purpose": {
                    "sft": "training",
                    "pretrain": "training",
                    "rag": "rag",
                    "evaluation": "evaluation",
                }[product],
                "config": cfg,
            },
        )
        for sample in call("GET", f"/dataset-builds/{build['build_id']}/candidates")["items"]:
            call(
                "POST",
                f"/candidate-samples/{sample['sample_id']}/reviews",
                {"decision": "approved", "note": "Reviewed original fixture and evidence"},
                who=reviewer,
            )
        assert call("POST", f"/dataset-builds/{build['build_id']}/validate", {})["ok"]
        return dataset_id, build["build_id"]

    def publish(dataset, build, label):
        release = call(
            "POST", f"/datasets/{dataset}/versions", {"build_id": build, "version": label}
        )
        manifest = call("GET", f"/datasets/{dataset}/versions/{label}/manifest")
        report = call("GET", f"/quality/reports/{release['dataset_version_id']}")
        assert report["sha256"] == manifest["quality_snapshot"]["report_sha256"]
        assert report["report"]["dataset_version_id"] == release["dataset_version_id"]
        purpose = manifest["purpose"]
        link = call("GET", f"/datasets/{dataset}/versions/{label}/download?purpose={purpose}")
        data = httpx.get(link["url"].replace("minio:9000", "127.0.0.1:59000"), timeout=20).content
        assert hashlib.sha256(data).hexdigest() == manifest["content"]["sha256"]
        return {
            **release,
            "dataset_id": dataset,
            "build_id": build,
            "version": label,
            "report": report,
            "manifest": manifest,
            "bytes": len(data),
        }

    for product, segs, cfg in [
        ("sft", train, {}),
        ("pretrain", train, {}),
        ("rag", rag, {"chunk_size": 5, "overlap": 1}),
        ("evaluation", evaluation, {}),
    ]:
        dataset, build = build_product(product, segs, cfg)
        result = publish(dataset, build, "1.0.0")
        evidence["products"][product] = result
        checked(f"{product}: publish, immutable quality snapshot, MinIO download hash")
    pretrain = evidence["products"]["pretrain"]
    dataset, second_build = build_product("pretrain", train[:1], dataset_id=pretrain["dataset_id"])
    second = publish(dataset, second_build, "2.0.0")
    comparison = call(
        "POST",
        "/quality/version-comparisons",
        {
            "left_version_id": pretrain["dataset_version_id"],
            "right_version_id": second["dataset_version_id"],
        },
    )
    evidence["comparison"] = comparison
    checked("two independent published builds compared without modifying either version")
    # Threshold change creates a new rule, evaluation and immutable report.
    first_sha = pretrain["report"]["sha256"]
    rule = call(
        "POST",
        "/quality/rules/versions",
        {
            "version": "2.0.0",
            "rules": {"document.metadata_completeness": {"enabled": True, "threshold": 1}},
        },
    )
    body = {
        "target_type": "dataset_version",
        "target_id": pretrain["dataset_version_id"],
        "idempotency_key": "repeat-evaluation",
    }
    evaluated = call("POST", "/quality/evaluations", body)
    repeated = call("POST", "/quality/evaluations", body)
    assert evaluated["evaluation_id"] == repeated["evaluation_id"]
    assert evaluated["report"]["quality_status"] == "FAIL"
    evidence["reevaluation"] = evaluated
    checked("rule revision, failed metadata quality, idempotent reevaluation")
    dataset, blocked = build_product("pretrain", train)
    failure = call(
        "POST",
        f"/datasets/{dataset}/versions",
        {"build_id": blocked, "version": "1.0.0"},
        status=409,
    )
    assert failure["error"]["code"] == "QUALITY_GATE_FAILED", failure
    checked("failed quality evaluation blocks new publication")
    with Session(engine) as db:
        old = db.get(DatasetQualityReport, pretrain["report"]["report_id"])
        assert old.report_sha256 == first_sha
        original = db.get(DatasetVersion, pretrain["dataset_version_id"])
        assert original.content_sha256 == pretrain["content_sha256"]
        assert not db.scalar(select(DatasetVersion.id).where(DatasetVersion.build_id == blocked))
        for table, ident, column in [
            ("dataset_quality_reports", old.id, "report_sha256"),
            ("quality_rule_versions", rule["id"], "config_hash"),
        ]:
            try:
                with db.begin_nested():
                    db.execute(
                        text(f"UPDATE {table} SET {column}='tampered' WHERE id=:id"), {"id": ident}
                    )
                raise AssertionError("immutable snapshot accepted update")
            except DBAPIError:
                pass
        # Only this script's newly created grant is changed, never existing user data.
        grant = db.scalar(
            select(LicenseGrant).where(
                LicenseGrant.asset_id == train_asset, LicenseGrant.purpose == "training"
            )
        )
        grant.status = "revoked"
        db.commit()
    denied = call(
        "POST",
        "/quality/evaluations",
        {"target_type": "dataset_version", "target_id": pretrain["dataset_version_id"]},
    )
    assert denied["report"]["authorization_gate"] == "FAIL"
    checked("revocation is independently denied; immutable DB snapshots resist updates")
    for path in [
        f"/quality/reports/{pretrain['dataset_version_id']}",
        f"/quality/evaluations/{evaluated['evaluation_id']}",
        f"/quality/version-comparisons/{comparison['comparison_id']}",
        f"/quality/ratios/{pretrain['dataset_version_id']}",
        f"/quality/coverage?dataset_version_id={pretrain['dataset_version_id']}",
    ]:
        call("GET", path, who=other, status=404)
    checked("cross-workspace report, evaluation, comparison, ratios and filtered coverage denied")
    evidence["coverage"] = call("GET", "/quality/coverage")
    assert evidence["coverage"]["asset_count"] == 3
    assert evidence["coverage"]["domain_label_occurrences"]["cryptography/hash"] == 6
    assert evidence["coverage"]["domain_unique_assets"]["cryptography/hash"] == 3
    checked("multi-label occurrences differ from unique assets")
    destination = ROOT / ".local/p1c"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    (destination / "web.json").write_text(
        json.dumps(
            {
                "session": admin,
                "left": pretrain["dataset_version_id"],
                "right": second["dataset_version_id"],
                "comparison_id": comparison["comparison_id"],
            }
        )
    )
    print(
        f"P1-C QUALITY PASS: {len(evidence['checks'])} real checks; "
        "evidence .local/p1c/evidence.json"
    )
    client.close()
    engine.dispose()


if __name__ == "__main__":
    main()
