"""Read-only export of synthetic fixture provenance. Reset means a new test workspace."""

import hashlib
import json
from pathlib import Path

from corpusflow.core.config import load_settings
from corpusflow.db.models import Asset, AssetBlob, Document, DocumentVersion, NodeRun, PipelineRun
from corpusflow.db.session import build_engine
from sqlalchemy import select
from sqlalchemy.orm import Session


def main():
    fixture = json.loads(Path("tests/fixtures/p1d/corpus.json").read_text())
    crypto = "\n".join(f"<h2>{t}</h2><p>{f}</p>" for t, f, _ in fixture["facts"]).encode()
    groups = [
        ("normal", Path("tests/fixtures/p1a/plain_text.pdf").read_bytes()),
        ("failure", b"this is not a PDF"),
        ("retrieval", crypto),
    ]
    manifest = []
    with Session(build_engine(load_settings())) as db:
        for kind, raw in groups:
            sha = hashlib.sha256(raw).hexdigest()
            asset = db.scalar(
                select(Asset)
                .join(AssetBlob)
                .where(AssetBlob.sha256 == sha)
                .order_by(Asset.created_at.desc())
            )
            assert asset is not None, (kind, "Run real Web E2E first")
            runs = list(db.scalars(select(PipelineRun).where(PipelineRun.asset_id == asset.id)))
            versions = list(
                db.scalars(
                    select(DocumentVersion).join(Document).where(Document.asset_id == asset.id)
                )
            )
            manifest.append(
                {
                    "group": kind,
                    "sha256": sha,
                    "bytes": len(raw),
                    "license": "repository-authored synthetic fixture; demo only",
                    "workspace_id": asset.workspace_id,
                    "asset_id": asset.id,
                    "runs": [
                        {
                            "run_id": r.id,
                            "status": r.status,
                            "config": r.config_snapshot,
                            "nodes": [
                                {"node_run_id": n.id, "status": n.status}
                                for n in db.scalars(select(NodeRun).where(NodeRun.run_id == r.id))
                            ],
                        }
                        for r in runs
                    ],
                    "document_version_ids": [v.id for v in versions],
                }
            )
    out = Path("docs/demo/DEMO_EVIDENCE.json")
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("PASS: three actual fixture groups; no records modified")


if __name__ == "__main__":
    main()
