"""M1 network checks, invoked only by the disposable --catalog verification harness."""

import json
import os
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from corpusflow.contracts.training_center import models as m
from corpusflow.db.models import LineageEdge, Membership, User
from corpusflow.modules.training_center.catalog import GeneratedCatalog
from corpusflow.modules.training_center.generation import (
    build_catalog,
    json_bytes,
    sha256,
    write_catalog,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/api/v1/training-center"


def main():
    context_path = Path(os.environ["M1_CATALOG_CONTEXT"]).resolve()
    reports = context_path.parent
    root = Path(os.environ["TRAINING_CENTER_DATA_DIR"]).resolve()
    base = os.environ["M0_LIVE_API"]
    if (
        reports.parent != ROOT / ".local"
        or not reports.name.startswith("cf-m1-")
        or root != reports / "catalog"
        or urlsplit(base).hostname != "127.0.0.1"
    ):
        raise SystemExit("Use verify_training_center_m0.py --catalog with its isolated resources")
    checks = []
    result = {"status": "running", "checks": checks}
    store = GeneratedCatalog(root)
    client = httpx.Client(base_url=base, timeout=30, trust_env=False)

    def call(path, status=200, *, headers=None, params=None, data=None, code=None, model=None):
        start = time.perf_counter()
        response = client.request(
            "POST" if data is not None else "GET",
            path,
            params=params,
            json=data,
            headers={"X-Request-ID": "m1-http-check", **(headers or {})},
        )
        checks.append(
            {
                "path": path,
                "status": response.status_code,
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        assert response.status_code == status, (path, response.status_code, response.text[:500])
        assert response.headers["X-Request-ID"] == "m1-http-check"
        body = response.json()
        if code:
            error = m.ApiErrorBody.model_validate(body)
            assert error.error.code == code
            assert error.request_id == "m1-http-check"
            assert str(root) not in response.text
        if model:
            model.model_validate(body)
        return body

    def login(suffix):
        user = reports.name + "-" + suffix
        session = call(
            "/api/v1/auth/session",
            data={"user_id": user, "display_name": user, "workspace_name": user},
        )
        return session, {
            "Authorization": "Bearer " + session["token"],
            "X-Workspace-ID": session["workspace_id"],
        }

    def publish(workspace, seed, counts):
        manifest, content = build_catalog(workspace, seed, *counts)
        directory = write_catalog(root / workspace / manifest["revision"], manifest, content)
        store.publish(workspace, manifest["revision"])
        return json.loads((directory / "manifest.json").read_bytes()), content, directory

    try:
        owner, auth = login("owner")
        other, other_auth = login("other")
        viewer, viewer_auth = login("viewer")
        missing, missing_auth = login("unpublished")
        workspace = owner["workspace_id"]
        manifest, content, _ = publish(workspace, 42, (2000, 1500, 800))
        other_manifest, other_content, _ = publish(other["workspace_id"], 43, (23, 11, 7))
        revision = manifest["revision"]
        scope_params = {"catalog": "generated", "revision": revision}
        raw_files = [json.loads(line) for line in content["files.jsonl"].splitlines()]
        raw_files.sort(key=lambda row: (row["filename"], row["id"]))
        source_counts = dict(Counter(row["source_kind"] for row in raw_files))
        call(PREFIX + "/overview", 401, code="UNAUTHENTICATED")
        call(
            PREFIX + "/overview",
            403,
            headers={**other_auth, "X-Workspace-ID": workspace},
            code="PERMISSION_DENIED",
        )
        call(PREFIX + "/overview", 404, headers=missing_auth, code="NOT_FOUND")
        overview = call(PREFIX + "/overview", headers=auth, model=m.OverviewResponse)
        assert overview["scope"]["workspace_id"] == workspace
        assert overview["scope"]["revision"] == revision
        assert overview["metrics"]["training_record_count"]["value"] == 4300
        assert overview["metrics"]["file_count"]["value"] == 860
        assert overview["metrics"]["token_count"]["value"] is None
        assert sum(row["file_count"] for row in overview["formats"]) == 860
        for fmt, expected in (("txt", 860), ("all", 860), ("pdf", 0), ("other", 0)):
            stats = call(
                PREFIX + f"/formats/{fmt}/stats",
                headers=auth,
                params=scope_params,
                model=m.FormatStatsResponse,
            )
            assert stats["metrics"]["file_count"]["value"] == expected
        source = raw_files[0]["source_kind"]
        stats = call(
            PREFIX + "/formats/txt/stats",
            headers=auth,
            params={**scope_params, "source_kind": source},
            model=m.FormatStatsResponse,
        )
        page = call(
            PREFIX + "/files",
            headers=auth,
            params={**scope_params, "source_kind": source, "offset": 1, "limit": 2},
            model=m.FilesResponse,
        )
        assert (
            page["total_count"] == stats["metrics"]["file_count"]["value"] == source_counts[source]
        )
        expected = [row["id"] for row in raw_files if row["source_kind"] == source][1:3]
        assert [row["id"] for row in page["items"]] == expected
        search = call(
            PREFIX + "/files",
            headers=auth,
            params={**scope_params, "q": raw_files[0]["filename"]},
            model=m.FilesResponse,
        )
        assert search["total_count"] == 1 and search["items"][0]["id"] == raw_files[0]["id"]
        page = call(
            PREFIX + "/files",
            headers=auth,
            params={**scope_params, "offset": 900},
            model=m.FilesResponse,
        )
        assert page["total_count"] == 860 and page["items"] == []
        detail = call(
            PREFIX + f"/files/{raw_files[0]['id']}",
            headers=auth,
            params=scope_params,
            model=m.FileDetailResponse,
        )
        assert detail["file"]["workspace_id"] == workspace
        assert detail["processing_summary_ref"] is None and "relative_path" not in detail["file"]
        call(
            PREFIX + f"/files/{raw_files[0]['id']}/comparison",
            404,
            headers=auth,
            params=scope_params,
            code="COMPARISON_NOT_AVAILABLE",
        )
        foreign_file = json.loads(other_content["files.jsonl"].splitlines()[0])["id"]
        call(PREFIX + f"/files/{foreign_file}", 404, headers=auth, code="NOT_FOUND")
        datasets = call(
            PREFIX + "/datasets", headers=auth, params=scope_params, model=m.DatasetsResponse
        )["items"]
        assert len(datasets) == 3
        for dataset in datasets:
            kind = dataset["kind"]
            base_path = PREFIX + f"/datasets/{dataset['id']}"
            params = {**scope_params, "version": dataset["version"]}
            expected_samples = [
                json.loads(line) for line in content[f"datasets/{kind}.jsonl"].splitlines()
            ]
            total = len(expected_samples)
            response = call(
                base_path + "/overview",
                headers=auth,
                params=params,
                model=m.DatasetOverviewResponse,
            )
            assert response["dataset"]["record_count"] == total
            assert sum(response["split_counts"].values()) == total
            page = call(
                base_path + "/samples",
                headers=auth,
                params={**params, "split": "train", "offset": 2, "limit": 7},
                model=m.SamplesResponse,
            )
            assert (
                len(page["items"]) == 7 and page["total_count"] == response["split_counts"]["train"]
            )
            assert all(
                row["kind"] == kind and row["workspace_id"] == workspace for row in page["items"]
            )
            empty = call(
                base_path + "/samples",
                headers=auth,
                params={**params, "q": "no-matching-training-record"},
                model=m.SamplesResponse,
            )
            assert empty["total_count"] == 0 and empty["items"] == []
            document = call(
                base_path + "/manifest", headers=auth, params=params, model=m.ManifestResponse
            )
            assert document["content_hash"] == sha256(json_bytes(manifest))
            assert document["manifest"] == manifest
        for path, params, status, code in (
            ("/files", {"limit": 101}, 422, "VALIDATION_FAILED"),
            ("/files", {"offset": -1}, 422, "VALIDATION_FAILED"),
            ("/files", {"revision": "../escape"}, 422, "INVALID_ARGUMENT"),
            ("/overview", {"revision": "a" * 64}, 409, "SNAPSHOT_EXPIRED"),
            ("/overview", {"catalog": "workspace"}, 503, "ADAPTER_UNAVAILABLE"),
            ("/formats/txt/stats", {"timezone": "Bad/Zone"}, 422, "INVALID_ARGUMENT"),
            ("/datasets/missing/samples", {}, 422, "VALIDATION_FAILED"),
            ("/datasets/missing/export", {}, 404, "NOT_FOUND"),
        ):
            call(PREFIX + path, status, headers=auth, params=params, code=code)
        # Independent real membership checks on a warm API cache, using this disposable DB only.
        call(
            f"/api/v1/workspaces/{workspace}/members",
            headers=auth,
            data={"user_id": viewer["token"], "role": "viewer"},
        )
        viewer_auth["X-Workspace-ID"] = workspace
        call(PREFIX + "/overview", headers=viewer_auth, model=m.OverviewResponse)
        engine = create_engine(os.environ["DATABASE_URL"])
        try:
            # Seed only explicit test lineage in the disposable database, not Worker history.
            source_ids = [
                call(
                    "/api/v1/sources",
                    headers=auth,
                    data={"name": f"isolated-graph-{index}", "kind": "other"},
                )["source_id"]
                for index in range(3)
            ]
            listed_sources = call("/api/v1/sources", headers=auth)
            assert set(source_ids) <= {row["source_id"] for row in listed_sources["items"]}
            with Session(engine) as session:
                session.add(
                    LineageEdge(
                        workspace_id=workspace,
                        from_type="Source",
                        from_id=source_ids[0],
                        to_type="Source",
                        to_id=source_ids[1],
                        relation="provides",
                    )
                )
                session.commit()
            graph_params = {
                "catalog": "workspace",
                "root_type": "source",
                "root_id": source_ids[0],
            }
            graph_path = "/api/v1/lineage/graph"
            graph = call(graph_path, headers=auth, params=graph_params, model=m.LineageGraph)
            assert {node["ref"]["id"] for node in graph["nodes"]} == set(source_ids[:2])
            assert {edge["relation"] for edge in graph["edges"]} == {"provides"}
            graph_revision = graph["scope"]["revision"]
            with Session(engine) as session:
                session.add(
                    LineageEdge(
                        workspace_id=workspace,
                        from_type="Source",
                        from_id=source_ids[1],
                        to_type="Source",
                        to_id=source_ids[2],
                        relation="provides",
                    )
                )
                session.commit()
            frozen = call(
                graph_path,
                headers=auth,
                params={**graph_params, "revision": graph_revision},
                model=m.LineageGraph,
            )
            assert frozen == graph
            latest = call(graph_path, headers=auth, params=graph_params, model=m.LineageGraph)
            assert {node["ref"]["id"] for node in latest["nodes"]} == set(source_ids)
            call(
                graph_path,
                409,
                headers=auth,
                params={**graph_params, "revision": "missing-graph-snapshot"},
                code="SNAPSHOT_EXPIRED",
            )
            call(graph_path, 404, headers=other_auth, params=graph_params, code="NOT_FOUND")
            generated_snapshot = store.load(workspace)
            generated_root = next(iter(generated_snapshot.sources))
            generated_graph = call(
                graph_path,
                headers=auth,
                params={
                    "catalog": "generated",
                    "root_type": "source",
                    "root_id": generated_root,
                    "revision": generated_snapshot.scope.revision,
                },
                model=m.LineageGraph,
            )
            assert generated_graph["scope"]["revision"] == generated_snapshot.scope.revision
            assert all(node["kind"] != "operator_run" for node in generated_graph["nodes"])
            with Session(engine) as session:
                membership = session.scalar(
                    select(Membership).where(
                        Membership.user_id == viewer["user_id"],
                        Membership.workspace_id == workspace,
                    )
                )
                membership.status = "revoked"
                session.commit()
            call(PREFIX + "/overview", 403, headers=viewer_auth, code="PERMISSION_DENIED")
            call(
                graph_path,
                403,
                headers=viewer_auth,
                params={**graph_params, "revision": graph_revision},
                code="PERMISSION_DENIED",
            )
            with Session(engine) as session:
                session.get(User, viewer["user_id"]).disabled = True
                session.commit()
            call(PREFIX + "/overview", 401, headers=viewer_auth, code="UNAUTHENTICATED")
        finally:
            engine.dispose()
        # Publication/retirement and corruption checks stay in the second workspace.
        second, _, _ = publish(other["workspace_id"], 44, (0, 0, 0))
        empty = call(PREFIX + "/overview", headers=other_auth, model=m.OverviewResponse)
        assert empty["metrics"]["training_record_count"]["value"] == 0
        assert len(empty["datasets"]) == 3
        pinned = call(
            PREFIX + "/overview",
            headers=other_auth,
            params={"revision": other_manifest["revision"]},
            model=m.OverviewResponse,
        )
        assert pinned["metrics"]["training_record_count"]["value"] == 41
        third, _, directory = publish(other["workspace_id"], 45, (1, 1, 1))
        store.retire(other["workspace_id"], other_manifest["revision"])
        call(
            PREFIX + "/overview",
            409,
            headers=other_auth,
            params={"revision": other_manifest["revision"]},
            code="SNAPSHOT_EXPIRED",
        )
        call(PREFIX + "/overview", headers=other_auth, params={"revision": second["revision"]})
        assert (root / other["workspace_id"] / other_manifest["revision"]).is_dir()
        call(PREFIX + "/overview", headers=other_auth, params={"revision": third["revision"]})
        path = directory / "datasets/cpt.jsonl"
        original = path.read_bytes()
        try:
            path.write_bytes(b"corrupt\n")
            call(PREFIX + "/overview", 409, headers=other_auth, code="CHECKSUM_MISMATCH")
            with path.open("wb") as stream:
                stream.truncate(100 * 1024 * 1024 + 1)
            call(PREFIX + "/overview", 413, headers=other_auth, code="CATALOG_LIMIT_EXCEEDED")
        finally:
            path.write_bytes(original)
        assert call(PREFIX + "/overview", headers=auth)["scope"]["revision"] == revision
        context = {
            "user_id": owner["token"],
            "workspace_name": owner["token"],
            "workspace_id": workspace,
            "revision": revision,
            "file_count": 860,
            "record_count": 4300,
            "first_file": raw_files[0],
            "source_counts": source_counts,
            "datasets": datasets,
            "graph_root_id": source_ids[0],
            "graph_revision": latest["scope"]["revision"],
        }
        context_path.write_text(
            json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        result.update(
            status="passed",
            workspace_id=workspace,
            revision=revision,
            request_count=len(checks),
            record_count=4300,
        )
    finally:
        client.close()
        if result["status"] == "running":
            result["status"] = "failed"
        (reports / "catalog-http.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"M1 HTTP verification: {result['status']}; {len(checks)} network requests")


if __name__ == "__main__":
    main()
