"""Real router + on-disk catalogs + existing authorization using disposable SQLite.

The production create_app registers the router; only the database dependency is isolated here.
"""

from __future__ import annotations

import pytest
from corpusflow.contracts.training_center import models as m
from corpusflow.db.models import Membership, User, Workspace
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
    for model in (User, Workspace, Membership):
        model.__table__.create(engine)
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
        ("/files", {"catalog": "workspace"}, 503, "ADAPTER_UNAVAILABLE"),
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
