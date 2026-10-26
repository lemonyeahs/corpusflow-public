import pytest
from corpusflow.api.v1.lineage_graph import (
    WORKSPACE_MODELS,
    FrozenEdge,
    GraphSnapshots,
    _stored_graph,
    router,
)
from corpusflow.contracts.training_center.models import GraphQuery, ObjectRef
from corpusflow.db.models import LineageEdge, Membership, Source, User, Workspace
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _row(from_type: str, from_id: str, to_type: str, to_id: str, relation: str) -> LineageEdge:
    return LineageEdge(
        workspace_id="workspace-1",
        from_type=from_type,
        from_id=from_id,
        to_type=to_type,
        to_id=to_id,
        relation=relation,
    )


def test_graph_router_exposes_contract_path() -> None:
    assert any(route.path == "/api/v1/lineage/graph" for route in router.routes)


@pytest.mark.parametrize("relation", ["provides", "parsed_by"])
def test_canonical_relations_are_not_relabelled_as_derivation(relation):
    graph = _stored_graph(
        [_row("Source", "source-1", "Asset", "asset-1", relation)],
        "workspace",
        "workspace-1",
        ObjectRef(catalog="workspace", type="source", id="source-1"),
        GraphQuery(catalog="workspace", root_type="source", root_id="source-1"),
        revision="frozen-revision",
        as_of="2026-10-27T00:00:00Z",
    )
    assert [edge.relation for edge in graph.edges] == [relation]


def test_stored_graph_adapts_workspace_rows_to_wire_contract() -> None:
    rows = [
        _row("Asset", "asset-1", "PipelineRun", "run-1", "processed_by"),
        _row("PipelineRun", "run-1", "DocumentVersion", "doc-1", "produced"),
    ]
    query = GraphQuery(
        catalog="workspace",
        root_type="file",
        root_id="asset-1",
        direction="downstream",
        max_depth=2,
        max_nodes=20,
    )

    graph = _stored_graph(
        rows,
        "workspace",
        "workspace-1",
        ObjectRef(catalog="workspace", type="file", id="asset-1"),
        query,
        revision="frozen-revision",
        as_of="2026-10-27T00:00:00Z",
    )

    assert graph.root.id == "asset-1"
    assert {(node.kind, node.ref.id) for node in graph.nodes} == {
        ("file", "asset-1"),
        ("operator_run", "run-1"),
        ("file", "doc-1"),
    }
    assert {(edge.source, edge.target, edge.relation) for edge in graph.edges} == {
        ("workspace:file:asset-1", "workspace:operator_run:run-1", "processed_by"),
        ("workspace:operator_run:run-1", "workspace:file:doc-1", "produced"),
    }
    assert graph.scope.workspace_id == "workspace-1"
    assert graph.scope.catalog == "workspace"


def test_stored_graph_marks_node_limit_and_keeps_endpoints_valid() -> None:
    rows = [
        _row("Asset", "asset-1", "PipelineRun", "run-1", "processed_by"),
        _row("Asset", "asset-1", "DocumentVersion", "doc-1", "parsed_to"),
    ]
    query = GraphQuery(
        catalog="workspace",
        root_type="file",
        root_id="asset-1",
        direction="downstream",
        max_depth=2,
        max_nodes=2,
    )

    graph = _stored_graph(
        rows,
        "workspace",
        "workspace-1",
        ObjectRef(catalog="workspace", type="file", id="asset-1"),
        query,
        revision="frozen-revision",
        as_of="2026-10-27T00:00:00Z",
    )

    assert graph.truncated is True
    assert graph.truncation_reason == "max_nodes"
    node_ids = {node.id for node in graph.nodes}
    assert all(edge.source in node_ids and edge.target in node_ids for edge in graph.edges)


def test_snapshots_expire_at_900_seconds_without_read_renewal():
    now = [0.0]
    store = GraphSnapshots(clock=lambda: now[0])
    snapshot = store.put("workspace-1", (), frozenset())
    now[0] = 899.999
    assert store.get("workspace-1", snapshot.revision) == snapshot
    now[0] = 900
    with pytest.raises(HTTPException) as error:
        store.get("workspace-1", snapshot.revision)
    assert (error.value.status_code, error.value.detail) == (409, "SNAPSHOT_EXPIRED")


def test_snapshots_evict_oldest_per_workspace_without_read_promoting():
    store = GraphSnapshots()
    first = store.put("workspace-1", (), frozenset())
    other = store.put("workspace-2", (), frozenset())
    for _ in range(9):
        store.put("workspace-1", (), frozenset())
    store.get("workspace-1", first.revision)
    newest = store.put("workspace-1", (), frozenset())
    with pytest.raises(HTTPException) as error:
        store.get("workspace-1", first.revision)
    assert error.value.status_code == 409
    assert store.get("workspace-1", newest.revision) == newest
    assert store.get("workspace-2", other.revision) == other
    with pytest.raises(HTTPException):
        store.get("workspace-2", newest.revision)


@pytest.fixture
def graph_api(settings):
    from corpusflow.api.dependencies import db
    from corpusflow.main import create_app

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models = {User, Workspace, Membership, LineageEdge, *WORKSPACE_MODELS.values()}
    for model in models:
        model.__table__.create(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(id="user-a", oidc_sub="token-a", display_name="A"),
                User(id="user-b", oidc_sub="token-b", display_name="B"),
                Workspace(id="workspace-a", slug="a", name="A"),
                Workspace(id="workspace-b", slug="b", name="B"),
                Membership(user_id="user-a", workspace_id="workspace-a", role="viewer"),
                Membership(user_id="user-b", workspace_id="workspace-b", role="viewer"),
                Source(id="source-a", workspace_id="workspace-a", name="A", kind="other"),
                Source(id="source-a2", workspace_id="workspace-a", name="A2", kind="other"),
                Source(id="source-b", workspace_id="workspace-b", name="B", kind="other"),
                LineageEdge(
                    workspace_id="workspace-a",
                    from_type="Source",
                    from_id="source-a",
                    to_type="Source",
                    to_id="source-a2",
                    relation="contains",
                ),
                # Corrupt cross-workspace reference must never expose the other source.
                LineageEdge(
                    workspace_id="workspace-a",
                    from_type="Source",
                    from_id="source-a",
                    to_type="Source",
                    to_id="source-b",
                    relation="contains",
                ),
            ]
        )
        session.commit()

    def database():
        with Session(engine) as session:
            yield session

    app = create_app(settings)
    app.dependency_overrides[db] = database
    try:
        with TestClient(app) as client:
            client.headers.update(
                {"Authorization": "Bearer token-a", "X-Workspace-ID": "workspace-a"}
            )
            yield client, engine
    finally:
        engine.dispose()


GRAPH_URL = "/api/v1/lineage/graph"
GRAPH_PARAMS = {"catalog": "workspace", "root_type": "source", "root_id": "source-a"}


def test_http_snapshot_preserves_rows_nodes_scope_and_supports_another_root(graph_api):
    client, engine = graph_api
    first = client.get(GRAPH_URL, params=GRAPH_PARAMS)
    assert first.status_code == 200, first.text
    frozen = first.json()
    assert {node["ref"]["id"] for node in frozen["nodes"]} == {"source-a", "source-a2"}
    revision = frozen["scope"]["revision"]
    store = client.app.state.lineage_snapshots
    snapshot = store.get("workspace-a", revision)
    assert all(isinstance(row, FrozenEdge) for row in snapshot.rows)
    with Session(engine) as session:
        session.execute(delete(LineageEdge))
        session.execute(delete(Source).where(Source.id == "source-a2"))
        session.commit()
    pinned = client.get(GRAPH_URL, params={**GRAPH_PARAMS, "revision": revision})
    assert pinned.json() == frozen
    other_root = client.get(
        GRAPH_URL, params={**GRAPH_PARAMS, "revision": revision, "root_id": "source-a2"}
    )
    assert other_root.status_code == 200
    assert other_root.json()["scope"] == frozen["scope"]
    fresh = client.get(GRAPH_URL, params=GRAPH_PARAMS)
    assert fresh.status_code == 200  # Visible isolated roots remain queryable.
    assert len(fresh.json()["nodes"]) == 1
    assert fresh.json()["edges"] == []
    assert fresh.json()["scope"]["revision"] != revision
    assert client.get(GRAPH_URL, params={**GRAPH_PARAMS, "root_id": "source-a2"}).status_code == 404


def test_http_snapshots_bound_to_workspace_and_auth_rechecked(graph_api):
    client, engine = graph_api
    revision = client.get(GRAPH_URL, params=GRAPH_PARAMS).json()["scope"]["revision"]
    params = {**GRAPH_PARAMS, "revision": revision}
    for root in ("source-a", "source-b", "missing"):
        response = client.get(
            GRAPH_URL,
            params={**params, "root_id": root},
            headers={"Authorization": "Bearer token-b", "X-Workspace-ID": "workspace-b"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SNAPSHOT_EXPIRED"
    assert client.get(GRAPH_URL, params={**params, "root_id": "source-b"}).status_code == 404
    assert (
        client.get(
            GRAPH_URL, params=params, headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    with Session(engine) as session:
        member = session.scalar(select(Membership).where(Membership.user_id == "user-a"))
        member.status = "revoked"
        session.commit()
    assert client.get(GRAPH_URL, params=params).status_code == 403


def test_http_expired_snapshot_and_generated_catalog_errors(graph_api):
    client, _ = graph_api
    now = [0.0]
    client.app.state.lineage_snapshots = GraphSnapshots(clock=lambda: now[0])
    revision = client.get(GRAPH_URL, params=GRAPH_PARAMS).json()["scope"]["revision"]
    now[0] = 900
    expired = client.get(GRAPH_URL, params={**GRAPH_PARAMS, "revision": revision})
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "SNAPSHOT_EXPIRED"
    unavailable = client.get(GRAPH_URL, params={**GRAPH_PARAMS, "catalog": "generated"})
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "CATALOG_UNAVAILABLE"
