"""Real router + on-disk catalogs + existing authorization using disposable SQLite.

The production create_app registers the router; only the database dependency is isolated here.
"""

from __future__ import annotations

import pytest
from corpusflow.contracts.training_center import models as m
from corpusflow.db.models import Membership, User, Workspace
from corpusflow.db.session import Base
from corpusflow.modules.training_center.catalog import GeneratedCatalog
from corpusflow.modules.training_center.generation import build_catalog, write_catalog
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def api(tmp_path, settings):
    from corpusflow.api.dependencies import db
    from corpusflow.main import create_app

    store = GeneratedCatalog(tmp_path)
    for workspace in ("workspace-a", "workspace-b"):
        manifest, content = build_catalog(workspace, 42, 23, 11, 7)
        write_catalog(tmp_path / workspace / manifest["revision"], manifest, content)
        store.publish(workspace, manifest["revision"])
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(id="user-a", oidc_sub="token-a", display_name="A"),
                User(id="user-b", oidc_sub="token-b", display_name="B"),
                Workspace(id="workspace-a", slug="a", name="A"),
                Workspace(id="workspace-b", slug="b", name="B"),
                Membership(
                    user_id="user-a", workspace_id="workspace-a", role="viewer", status="active"
                ),
                Membership(
                    user_id="user-b", workspace_id="workspace-b", role="engineer", status="active"
                ),
            ]
        )
        session.commit()

    def database():
        with Session(engine) as session:
            yield session

    app = create_app(settings.model_copy(update={"training_center_data_dir": tmp_path}))
    app.dependency_overrides[db] = database
    try:
        with TestClient(app) as client:
            client.headers.update(
                {
                    "Authorization": "Bearer token-a",
                    "X-Workspace-ID": "workspace-a",
                    "X-Request-ID": "catalog-http-test",
                }
            )
            yield client, store, engine
    finally:
        engine.dispose()


PREFIX = "/api/v1/training-center"


@pytest.mark.parametrize(
    "invalid",
    [
        {"version": ""},
        {"catalog": "other"},
        {"split": "other"},
        {"export_format": "other"},
        {"limit": 1},
    ],
)
def test_export_rejects_invalid_query(api, invalid):
    client, store, _ = api
    dataset = store.load("workspace-a").datasets[0]
    response = client.get(
        f"{PREFIX}/datasets/{dataset.id}/export",
        params={"version": dataset.version, **invalid},
    )
    assert response.status_code == 422


def test_filtered_exports_and_off_page_details(api):
    import json

    client, store, _ = api
    snapshot = store.load("workspace-a")
    for dataset in snapshot.datasets:
        base = f"{PREFIX}/datasets/{dataset.id}"
        params = {"revision": snapshot.scope.revision, "version": dataset.version, "q": "第"}
        first = client.get(base + "/samples", params={**params, "limit": 2}).json()
        assert first["total_count"] > 2
        pages = []
        for offset in range(0, first["total_count"], 2):
            pages.extend(
                client.get(
                    base + "/samples", params={**params, "offset": offset, "limit": 2}
                ).json()["items"]
            )
        response = client.get(base + "/export", params=params)
        assert response.status_code == 200, response.text
        assert "charset=utf-8" in response.headers["content-type"]
        assert [json.loads(line) for line in response.content.splitlines()] == pages
        detail = client.get(
            base + "/samples/" + pages[-1]["id"],
            params={"revision": snapshot.scope.revision, "version": dataset.version},
        )
        assert detail.status_code == 200 and detail.json()["items"] == [pages[-1]]
        assert (
            client.get(
                base + "/samples/" + pages[-1]["id"], params={"version": "missing"}
            ).status_code
            == 404
        )
        assert (
            client.get(base + "/samples/missing", params={"version": dataset.version}).status_code
            == 404
        )
        assert client.get(base + "/export", params={**params, "q": "没有匹配的内容"}).content == b""
        assert client.get(base + "/export", params={**params, "offset": 20}).status_code == 422


def test_workspace_database_http_snapshot_filter_export_and_revocation(api):
    import json

    from corpusflow.db import models as d

    client, _, engine = api
    wid = "workspace-a"
    with Session(engine) as session:
        session.add(d.Source(id="ws-source", workspace_id=wid, name="Book", kind="book"))
        session.add(
            d.AssetBlob(
                id="ws-blob",
                workspace_id=wid,
                storage_key="ws/file",
                sha256="a" * 64,
                byte_size=50,
                media_type="text/plain",
            )
        )
        session.add(
            d.Asset(
                id="ws-file",
                workspace_id=wid,
                source_id="ws-source",
                blob_id="ws-blob",
                filename="book.txt",
                format="txt",
                language="zh",
            )
        )
        session.add(d.Document(id="ws-doc", workspace_id=wid, asset_id="ws-file", title="Book"))
        session.add(
            d.DocumentVersion(
                id="ws-doc-version", workspace_id=wid, document_id="ws-doc", content_sha256="a" * 64
            )
        )
        session.add(
            d.Segment(
                id="ws-segment",
                workspace_id=wid,
                document_version_id="ws-doc-version",
                source_id="ws-source",
                text="正文",
                content_hash="a" * 64,
            )
        )
        session.add(
            d.Dataset(id="ws-dataset", workspace_id=wid, name="中文数据集", product_type="pretrain")
        )
        session.add(
            d.DatasetBuild(
                id="ws-build",
                workspace_id=wid,
                dataset_id="ws-dataset",
                created_by="user-a",
                config_json={},
                config_hash="a" * 64,
            )
        )
        session.add(
            d.DatasetVersion(
                id="ws-version",
                workspace_id=wid,
                dataset_id="ws-dataset",
                build_id="ws-build",
                version="1",
                manifest_sha256="a" * 64,
                content_sha256="b" * 64,
                published_by="user-a",
            )
        )
        for i in range(25):
            session.add(
                d.CandidateSample(
                    id=f"ws-sample-{i}",
                    workspace_id=wid,
                    build_id="ws-build",
                    sample_key=str(i),
                    source_id="ws-source",
                    payload={
                        "text": f'中文,"引号"\n匹配 {i}' if i < 22 else "其他",
                        "evidence_ids": ["ws-segment"],
                    },
                    payload_hash="a" * 64,
                )
            )
            session.add(
                d.DatasetVersionSample(
                    dataset_version_id="ws-version",
                    candidate_sample_id=f"ws-sample-{i}",
                    split="train",
                )
            )
        session.commit()
    overview = client.get(PREFIX + "/overview", params={"catalog": "workspace"}).json()
    params = {"catalog": "workspace", "revision": overview["scope"]["revision"]}
    assert overview["metrics"]["training_record_count"]["value"] == 25
    assert overview["metrics"]["segment_count"]["value"] == 1
    files = client.get(PREFIX + "/files", params=params).json()
    assert files["total_count"] == 1 and files["items"][0]["dataset_refs"][0]["id"] == "ws-version"
    stats = client.get(PREFIX + "/formats/txt/stats", params=params).json()
    assert stats["metrics"]["file_count"]["value"] == files["total_count"]
    base = PREFIX + "/datasets/ws-dataset"
    query = {**params, "version": "1", "split": "train", "q": "匹配"}
    first = client.get(base + "/samples", params=query).json()
    second = client.get(base + "/samples", params={**query, "offset": 20}).json()
    assert first["total_count"] == 22 and len(first["items"]) == 20 and len(second["items"]) == 2
    assert client.get(base + "/export", params=query).status_code == 403
    with Session(engine) as session:
        session.add(
            d.LicenseGrant(
                id="ws-grant",
                workspace_id=wid,
                asset_id="ws-file",
                purpose="training",
                status="confirmed",
            )
        )
        session.get(d.CandidateSample, "ws-sample-0").payload = {
            "text": "数据库已更新",
            "evidence_ids": ["ws-segment"],
        }
        session.commit()
    response = client.get(base + "/export", params=query)
    assert response.status_code == 200, response.text
    assert [json.loads(line) for line in response.content.splitlines()] == first["items"] + second[
        "items"
    ]
    assert client.get(base + "/samples", params={**query, "revision": "expired"}).status_code == 409
    assert (
        client.get(
            base + "/samples",
            params=query,
            headers={"Authorization": "Bearer token-b", "X-Workspace-ID": "workspace-b"},
        ).status_code
        == 409
    )
    with Session(engine) as session:
        session.get(d.LicenseGrant, "ws-grant").status = "revoked"
        session.commit()
    assert client.get(base + "/export", params=query).status_code == 403
    with Session(engine) as session:
        member = session.scalar(select(Membership).where(Membership.user_id == "user-a"))
        member.status = "revoked"
        session.commit()
    assert client.get(base + "/samples", params=query).status_code == 403


def test_workspace_provider_is_replaceable_without_changing_wire_scope(api):
    from corpusflow.api.v1.training_center import workspace_store
    from corpusflow.modules.training_center.workspace import WorkspaceSnapshots

    client, _, _ = api

    class Provider:
        calls = []
        backend = WorkspaceSnapshots()

        def load(self, workspace, revision, session, max_records, max_bytes):
            self.calls.append((workspace, revision))
            return self.backend.load(workspace, revision, session, max_records, max_bytes)

    provider = Provider()
    client.app.dependency_overrides[workspace_store] = lambda: provider
    first = client.get(PREFIX + "/overview", params={"catalog": "workspace"})
    revision = first.json()["scope"]["revision"]
    second = client.get(PREFIX + "/datasets", params={"catalog": "workspace", "revision": revision})
    assert first.json()["scope"] == second.json()["scope"]
    assert provider.calls == [("workspace-a", None), ("workspace-a", revision)]


def test_workspace_http_has_independent_frozen_empty_snapshot(api):
    client, _, _ = api
    first = client.get(PREFIX + "/overview", params={"catalog": "workspace"})
    assert first.status_code == 200, first.text
    parsed = m.OverviewResponse.model_validate(first.json())
    assert parsed.metrics["training_record_count"].value == 0
    assert parsed.scope.catalog == "workspace"
    params = {"catalog": "workspace", "revision": parsed.scope.revision}
    response = client.get(PREFIX + "/files", params=params)
    assert response.status_code == 200 and response.json()["items"] == []
    assert response.json()["scope"] == first.json()["scope"]
    cross_workspace = client.get(
        PREFIX + "/files",
        params=params,
        headers={"Authorization": "Bearer token-b", "X-Workspace-ID": "workspace-b"},
    )
    assert cross_workspace.status_code == 409
    assert cross_workspace.json()["error"]["code"] == "SNAPSHOT_EXPIRED"
    response = client.get(PREFIX + "/files", params={"catalog": "workspace", "revision": "missing"})
    assert response.status_code == 409


def test_export_http_uses_full_split_and_audits_only_success(api, monkeypatch):
    from types import SimpleNamespace

    from corpusflow.db.models import AuditEvent
    from corpusflow.modules.training_center import downloads

    client, store, engine = api
    snapshot = store.load("workspace-a")
    dataset = snapshot.datasets[0]
    captured = []

    def serializer(records, kind, export_format):
        captured.extend(records)
        return SimpleNamespace(
            chunks=iter([b"complete\n"]), content_type="text/plain", extension="txt"
        )

    monkeypatch.setattr(downloads, "serializer", serializer)
    params = {
        "version": dataset.version,
        "revision": snapshot.scope.revision,
        "export_format": "txt",
        "split": "train",
    }
    response = client.get(f"{PREFIX}/datasets/{dataset.id}/export", params=params)
    assert response.status_code == 200 and response.content == b"complete\n"
    assert int(response.headers["content-length"]) == 9
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert len(captured) == dataset.split_counts.train
    assert all(item["split"] == "train" for item in captured)
    with Session(engine) as session:
        audit = session.scalar(select(AuditEvent))
        assert audit.summary["revision"] == snapshot.scope.revision
        assert audit.summary["record_count"] == len(captured)


def test_export_unavailable_never_returns_success_headers(api, monkeypatch):
    from corpusflow.modules.training_center import downloads
    from corpusflow.modules.training_center.catalog import CatalogError

    client, store, _ = api
    dataset = store.load("workspace-a").datasets[0]

    def unavailable(*args):
        raise CatalogError("ADAPTER_UNAVAILABLE", 503)

    monkeypatch.setattr(downloads, "serializer", unavailable)
    response = client.get(
        f"{PREFIX}/datasets/{dataset.id}/export", params={"version": dataset.version}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ADAPTER_UNAVAILABLE"
    assert "content-disposition" not in response.headers


def test_real_agent3_exports_through_http(api):
    import json

    client, store, _ = api
    snapshot = store.load("workspace-a")
    for dataset in snapshot.datasets:
        for export_format, extension in (
            ("jsonl", "jsonl"),
            ("markdown", "md"),
            ("csv", "csv"),
            ("txt", "txt"),
        ):
            response = client.get(
                f"{PREFIX}/datasets/{dataset.id}/export",
                params={
                    "version": dataset.version,
                    "revision": snapshot.scope.revision,
                    "export_format": export_format,
                    "split": "train",
                },
            )
            assert response.status_code == 200, response.text
            assert f"filename=dataset.{extension}" in response.headers["content-disposition"]
            assert int(response.headers["content-length"]) == len(response.content)
            if export_format == "jsonl":
                rows = [json.loads(line) for line in response.content.splitlines()]
                assert len(rows) == dataset.split_counts.train
                assert all(row["kind"] == dataset.kind and row["split"] == "train" for row in rows)


def test_http_endpoints_use_verified_files_and_canonical_responses(api):
    client, store, _ = api
    snapshot = store.load("workspace-a")
    revision = snapshot.scope.revision
    responses = [
        ("/overview", {}, m.OverviewResponse),
        ("/formats/txt/stats", {"source_kind": "book"}, m.FormatStatsResponse),
        ("/files", {"offset": "1", "limit": "2"}, m.FilesResponse),
        (f"/files/{snapshot.files[0].id}", {}, m.FileDetailResponse),
        ("/datasets", {}, m.DatasetsResponse),
    ]
    for dataset in snapshot.datasets:
        base = f"/datasets/{dataset.id}"
        responses.extend(
            [
                (f"{base}/overview", {"version": dataset.version}, m.DatasetOverviewResponse),
                (
                    f"{base}/samples",
                    {"version": dataset.version, "split": "train", "offset": 1, "limit": 2},
                    m.SamplesResponse,
                ),
                (f"{base}/manifest", {"version": dataset.version}, m.ManifestResponse),
            ]
        )
    for path, params, model in responses:
        response = client.get(
            PREFIX + path, params={"catalog": "generated", "revision": revision, **params}
        )
        assert response.status_code == 200, response.text
        parsed = model.model_validate(response.json())
        assert parsed.scope == snapshot.scope
        assert response.headers["X-Request-ID"] == "catalog-http-test"
        assert "relative_path" not in response.json()  # File internals are not file-summary fields.
    assert (
        client.get(PREFIX + "/overview").json()["metrics"]["training_record_count"]["value"] == 41
    )


@pytest.mark.parametrize(
    "headers,status,code",
    [
        ({"Authorization": ""}, 401, "UNAUTHENTICATED"),
        ({"Authorization": "Bearer invalid"}, 401, "UNAUTHENTICATED"),
        ({"X-Workspace-ID": "workspace-b"}, 403, "PERMISSION_DENIED"),
        ({"X-Workspace-ID": "../workspace-b"}, 403, "PERMISSION_DENIED"),
    ],
)
def test_auth_runs_before_any_catalog_read(api, headers, status, code, monkeypatch):
    client, _, _ = api

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized filesystem access")

    monkeypatch.setattr(GeneratedCatalog, "load", forbidden)
    response = client.get(PREFIX + "/overview", headers=headers)
    assert response.status_code == status
    error = m.ApiErrorBody.model_validate(response.json())
    assert error.error.code == code
    assert error.request_id == "catalog-http-test"


def test_workspace_scoping_and_membership_revocation_even_with_warm_cache(api):
    client, store, engine = api
    first = client.get(PREFIX + "/overview")
    assert first.status_code == 200
    other = store.load("workspace-b")
    response = client.get(PREFIX + f"/files/{other.files[0].id}")
    assert response.status_code == 404
    response = client.get(PREFIX + "/overview", params={"revision": other.scope.revision})
    assert response.status_code == 409
    response = client.get(
        PREFIX + "/overview",
        headers={"Authorization": "Bearer token-b", "X-Workspace-ID": "workspace-b"},
    )
    assert response.json()["scope"]["workspace_id"] == "workspace-b"
    with Session(engine) as session:
        member = session.scalar(select(Membership).where(Membership.user_id == "user-a"))
        member.status = "revoked"
        session.commit()
    assert client.get(PREFIX + "/overview").status_code == 403


@pytest.mark.parametrize(
    "path,params,status,code",
    [
        ("/files", {"limit": 101}, 422, "VALIDATION_FAILED"),
        ("/files", {"offset": -1}, 422, "VALIDATION_FAILED"),
        ("/files", {"workspace_id": "workspace-b"}, 422, "VALIDATION_FAILED"),
        ("/files", {"revision": "../escape"}, 422, "INVALID_ARGUMENT"),
        ("/files", {"revision": "a" * 64}, 409, "SNAPSHOT_EXPIRED"),
        ("/formats/binary/stats", {}, 422, "VALIDATION_FAILED"),
        ("/formats/txt/stats", {"timezone": "Bad/Zone"}, 422, "INVALID_ARGUMENT"),
        ("/datasets/absent/samples", {}, 422, "VALIDATION_FAILED"),
        ("/datasets/absent/samples", {"version": "1"}, 404, "NOT_FOUND"),
    ],
)
def test_http_errors_are_explicit(api, path, params, status, code):
    response = api[0].get(PREFIX + path, params=params)
    assert response.status_code == status, response.text
    assert m.ApiErrorBody.model_validate(response.json()).error.code == code


def test_comparison_never_fabricates_processing(api):
    client, store, _ = api
    file = store.load("workspace-a").files[0]
    response = client.get(PREFIX + f"/files/{file.id}/comparison")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COMPARISON_NOT_AVAILABLE"
    response = client.get(PREFIX + "/files/missing/comparison")
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_missing_corrupt_and_over_limit_catalogs_never_fall_back(api):
    client, store, _ = api
    revision = store.load("workspace-a").scope.revision
    assert client.get(PREFIX + "/overview").status_code == 200
    path = store.root / "workspace-a" / revision / "datasets/cpt.jsonl"
    path.write_bytes(b"corrupt")
    response = client.get(PREFIX + "/overview")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHECKSUM_MISMATCH"
    assert str(store.root) not in response.text
    # An absent publication registry is not a valid empty catalog.
    (store.root / "workspace-a/catalog.json").unlink()
    assert client.get(PREFIX + "/overview").status_code == 404


def test_snapshot_is_pinned_across_active_revision_switch(api):
    client, store, _ = api
    old = client.get(PREFIX + "/overview").json()["scope"]
    manifest, content = build_catalog("workspace-a", 99, 1, 1, 1)
    write_catalog(store.root / "workspace-a" / manifest["revision"], manifest, content)
    store.publish("workspace-a", manifest["revision"])
    assert client.get(PREFIX + "/overview").json()["metrics"]["training_record_count"]["value"] == 3
    pinned = client.get(PREFIX + "/overview", params={"revision": old["revision"]}).json()
    assert pinned["scope"] == old
    assert pinned["metrics"]["training_record_count"]["value"] == 41


def test_limit_response_and_disabled_user(api):
    client, store, engine = api
    client.app.state.training_center_generated = GeneratedCatalog(store.root, max_records=1)
    response = client.get(PREFIX + "/overview")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "CATALOG_LIMIT_EXCEEDED"
    with Session(engine) as session:
        user = session.get(User, "user-a")
        user.disabled = True
        session.commit()
    assert client.get(PREFIX + "/overview").status_code == 401


def test_stats_http_from_alias_and_inverted_range(api):
    client = api[0]
    response = client.get(PREFIX + "/formats/txt/stats", params={"from": "2026-01-01T00:00:00Z"})
    assert response.status_code == 200
    assert response.json()["metrics"]["file_count"]["value"] == 0
    response = client.get(
        PREFIX + "/formats/txt/stats",
        params={
            "from": "2026-02-01T00:00:00Z",
            "to": "2026-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
