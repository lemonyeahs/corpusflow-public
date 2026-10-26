from corpusflow.api.v1.lineage_graph import _stored_graph, router
from corpusflow.contracts.training_center.models import GraphQuery, ObjectRef
from corpusflow.db.models import LineageEdge


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
    )

    assert graph.truncated is True
    assert graph.truncation_reason == "max_nodes"
    node_ids = {node.id for node in graph.nodes}
    assert all(edge.source in node_ids and edge.target in node_ids for edge in graph.edges)
