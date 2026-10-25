"""Exercise pretrain, RAG and evaluation products against the real Docker API/MinIO."""

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4

from corpusflow.core.config import load_settings
from corpusflow.db.models import Asset, Membership, Segment, User
from corpusflow.db.session import build_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BASE = "http://127.0.0.1:58000/api/v1"


def call(method: str, path: str, token: str, workspace: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": workspace,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> None:
    settings = load_settings()
    factory = sessionmaker(build_engine(settings), expire_on_commit=False)
    with factory() as session:
        admin = session.scalar(
            select(User)
            .where(User.oidc_sub.like("acceptance-admin-%"))
            .order_by(User.created_at.desc())
        )
        assert admin
        membership = session.scalar(
            select(Membership).where(Membership.user_id == admin.id).order_by(Membership.created_at)
        )
        segment = (
            session.scalar(
                select(Segment)
                .where(Segment.workspace_id == membership.workspace_id)
                .order_by(Segment.created_at.desc())
            )
            if membership
            else None
        )
        asset = (
            session.scalar(
                select(Asset)
                .where(Asset.workspace_id == membership.workspace_id)
                .order_by(Asset.created_at.desc())
            )
            if membership
            else None
        )
        reviewer = (
            session.scalar(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.workspace_id == membership.workspace_id,
                    Membership.role == "reviewer",
                )
                .order_by(User.created_at.desc())
            )
            if membership
            else None
        )
        assert membership and segment and reviewer and asset
        workspace = membership.workspace_id
    admin_token, reviewer_token = admin.oidc_sub, reviewer.oidc_sub
    for purpose in ("training", "rag", "evaluation"):
        status, body = call(
            "POST",
            "/authorization/grants",
            admin_token,
            workspace,
            {
                "asset_id": asset.id,
                "purpose": purpose,
                "evidence_uri": f"p1b://{purpose}",
                "legal_basis": "isolated fixture",
            },
        )
        if status not in (200, 409):
            raise AssertionError(body)
    products = {
        "pretrain": {"purpose": "training", "config": {}},
        "rag": {"purpose": "rag", "config": {"unit": "tokens", "chunk_size": 3, "overlap": 1}},
        "evaluation": {
            "purpose": "evaluation",
            "config": {
                "evaluation_samples": [
                    {
                        "question": "What is the source segment about?",
                        "reference_answer": (
                            "The source segment contains the reviewed document text."
                        ),
                        "evidence_ids": [segment.id],
                        "question_type": "open",
                        "difficulty": "easy",
                        "domain": "technical",
                    }
                ]
            },
        },
    }
    results = {}
    for product, spec in products.items():
        status, dataset = call(
            "POST",
            "/datasets",
            admin_token,
            workspace,
            {"name": f"p1b-{product}-{uuid4().hex[:8]}", "product_type": product},
        )
        assert status == 200, dataset
        status, build = call(
            "POST",
            "/dataset-builds",
            admin_token,
            workspace,
            {
                "dataset_id": dataset["dataset_id"],
                "segment_ids": [segment.id],
                "purpose": spec["purpose"],
                "config": spec["config"],
            },
        )
        assert status == 200, build
        candidates = call(
            "GET", f"/dataset-builds/{build['build_id']}/candidates", admin_token, workspace
        )[1]["items"]
        assert candidates, (product, build)
        for candidate in candidates:
            status, reviewed = call(
                "POST",
                f"/candidate-samples/{candidate['sample_id']}/reviews",
                reviewer_token,
                workspace,
                {"decision": "approved", "note": f"P1-B {product}"},
            )
            assert status == 200, reviewed
        status, validated = call(
            "POST", f"/dataset-builds/{build['build_id']}/validate", admin_token, workspace, {}
        )
        assert status == 200 and validated["ok"], (product, validated)
        version = f"2.0.{datetime.now(UTC).microsecond % 100000}"
        status, published = call(
            "POST",
            f"/datasets/{dataset['dataset_id']}/versions",
            admin_token,
            workspace,
            {"build_id": build["build_id"], "version": version},
        )
        assert status == 200, published
        duplicate_status, duplicate = call(
            "POST",
            f"/datasets/{dataset['dataset_id']}/versions",
            admin_token,
            workspace,
            {"build_id": build["build_id"], "version": version},
        )
        assert (
            duplicate_status == 200
            and duplicate["dataset_version_id"] == published["dataset_version_id"]
        )
        manifest = call(
            "GET",
            f"/datasets/{dataset['dataset_id']}/versions/{version}/manifest",
            admin_token,
            workspace,
        )[1]
        download = call(
            "GET",
            f"/datasets/{dataset['dataset_id']}/versions/{version}/download?purpose={spec['purpose']}",
            admin_token,
            workspace,
        )[1]
        signed_url = download["url"].replace("minio:9000", "127.0.0.1:59000")
        with urllib.request.urlopen(signed_url, timeout=30) as response:
            content = response.read()
        assert hashlib.sha256(content).hexdigest() == manifest["content"]["sha256"]
        assert manifest["product_type"] == product
        results[product] = {
            "dataset_id": dataset["dataset_id"],
            "version": version,
            "samples": manifest["sample_count"],
            "sha256": manifest["content"]["sha256"],
            "bytes": len(content),
        }
    mismatch_status, mismatch = call(
        "POST",
        "/datasets",
        admin_token,
        workspace,
        {"name": f"p1b-mismatch-{uuid4().hex[:8]}", "product_type": "pretrain"},
    )
    assert mismatch_status == 200
    mismatch_status, mismatch = call(
        "POST",
        "/dataset-builds",
        admin_token,
        workspace,
        {
            "dataset_id": mismatch["dataset_id"],
            "segment_ids": [segment.id],
            "purpose": "rag",
            "config": {},
        },
    )
    assert mismatch_status == 409 and mismatch["error"]["code"] == "PRODUCT_PURPOSE_MISMATCH", (
        mismatch_status,
        mismatch,
    )
    outsider_status, outsider = call(
        "POST",
        "/auth/session",
        "",
        "",
        {
            "user_id": f"p1b-outsider-{uuid4().hex[:8]}",
            "display_name": "P1-B outsider",
            "workspace_name": f"P1-B outside {uuid4().hex[:8]}",
        },
    )
    assert outsider_status == 200
    dataset_id = results["pretrain"]["dataset_id"]
    version = results["pretrain"]["version"]
    # The outsider has a separate workspace and cannot read the published manifest.
    denied_status, _ = call(
        "GET",
        f"/datasets/{dataset_id}/versions/{version}/manifest",
        outsider["token"],
        outsider["workspace_id"],
    )
    assert denied_status == 404
    print("P1-B PRODUCTS PASS")
    print(
        json.dumps(
            {"workspace": workspace, "segment_id": segment.id, "products": results},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
