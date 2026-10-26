import json
from pathlib import Path

import pytest
from corpusflow.modules.lineage_graph import GraphQueryError, query_graph

FIXTURE = Path(__file__).parents[1] / "fixtures" / "lineage_graph_fixture.json"


def _fixture():
    payload = json.loads(FIXTURE.read_text())
    return payload["edges"], payload["nodes"]


def _keys(result):
    return {(node.kind, node.id) for node in result.nodes}


def _edge_keys(result):
    return {
        (edge.source_kind, edge.source_id, edge.target_kind, edge.target_id, edge.relation)
        for edge in result.edges
    }


def test_single_node_query_has_root_only():
    edges, nodes = _fixture()
    result = query_graph(edges, ("DatasetVersion", "dataset-v1"), nodes=nodes, max_depth=0)
    assert _keys(result) == {("DatasetVersion", "dataset-v1")}
    assert result.edges == ()
    assert result.truncated is True
    assert result.truncation_reason == "max_depth"


def test_single_hop_upstream_keeps_edge_orientation():
    edges, nodes = _fixture()
    result = query_graph(
        edges, ("DatasetVersion", "dataset-v1"), nodes=nodes, direction="upstream", max_depth=1
    )
    assert _keys(result) == {
        ("DatasetVersion", "dataset-v1"),
        ("CandidateSample", "sample-1"),
        ("Segment", "segment-1"),
        ("Segment", "segment-2"),
        ("Source", "source-1"),
    }
    assert all(edge.target_id == "dataset-v1" for edge in result.edges)
    assert all(edge.source_kind != "DatasetVersion" for edge in result.edges)


def test_single_hop_downstream():
    edges, nodes = _fixture()
    result = query_graph(
        edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=1
    )
    assert _keys(result) == {
        ("Asset", "asset-a"),
        ("Asset", "asset-b"),
        ("PipelineRun", "run-1"),
    }


def test_two_hops_and_three_hops():
    edges, nodes = _fixture()
    one = query_graph(edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=1)
    two = query_graph(edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=2)
    three = query_graph(
        edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=3
    )
    assert ("DocumentVersion", "doc-v1") not in _keys(one)
    assert ("DocumentVersion", "doc-v1") in _keys(two)
    assert ("Segment", "segment-1") in _keys(three)


def test_linear_lineage_contains_expected_path():
    edges, nodes = _fixture()
    result = query_graph(
        edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=4
    )
    assert ("PipelineRun", "run-1", "DocumentVersion", "doc-v1", "produced") in _edge_keys(result)


def test_branch_and_merge_are_preserved_and_deduplicated():
    edges, nodes = _fixture()
    result = query_graph(
        edges, ("DocumentVersion", "doc-v1"), nodes=nodes, direction="downstream", max_depth=4
    )
    assert {("Segment", "segment-1"), ("Segment", "segment-2")} <= _keys(result)
    assert ("DatasetVersion", "dataset-v1") in _keys(result)
    assert len(result.edges) == len(_edge_keys(result))


def test_same_node_reached_by_multiple_paths_is_one_node():
    edges, nodes = _fixture()
    result = query_graph(
        edges, ("Source", "source-1"), nodes=nodes, direction="downstream", max_depth=6
    )
    assert sum(node.id == "dataset-v1" for node in result.nodes) == 1


def test_duplicate_edges_are_removed():
    edges, nodes = _fixture()
    duplicate = [*edges, edges[1], dict(edges[1])]
    result = query_graph(
        duplicate, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=1
    )
    assert len(result.edges) == 2


def test_cycle_is_safe():
    edges, nodes = _fixture()
    cyclic = [
        *edges,
        {
            "from_type": "DocumentVersion",
            "from_id": "doc-v1",
            "to_type": "Asset",
            "to_id": "asset-a",
            "relation": "cycle",
        },
    ]
    result = query_graph(cyclic, ("Asset", "asset-a"), nodes=nodes, max_depth=12)
    assert len(result.nodes) == len(_keys(result))
    assert len(result.edges) == len(_edge_keys(result))


def test_depth_boundary_marks_truncation_only_when_more_graph_exists():
    edges, nodes = _fixture()
    result = query_graph(
        edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=1
    )
    assert result.truncated is True
    assert result.truncation_reason == "max_depth"


def test_missing_root_is_rejected_when_registry_is_available():
    edges, nodes = _fixture()
    with pytest.raises(GraphQueryError, match="root node not found"):
        query_graph(edges, ("Asset", "missing"), nodes=nodes)


def test_wrong_entity_type_is_not_silently_coerced():
    edges, nodes = _fixture()
    with pytest.raises(GraphQueryError, match="root node not found"):
        query_graph(edges, ("NotAnObjectType", "asset-a"), nodes=nodes)


def test_dangling_edge_is_ignored():
    edges, nodes = _fixture()
    edges = [
        *edges,
        {
            "from_type": "Asset",
            "from_id": "asset-a",
            "to_type": "Segment",
            "to_id": "missing",
            "relation": "contains",
        },
    ]
    result = query_graph(
        edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=1
    )
    assert ("Segment", "missing") not in _keys(result)
    assert all(edge.target_id != "missing" for edge in result.edges)


def test_invalid_direction_and_parameters():
    edges, nodes = _fixture()
    with pytest.raises(GraphQueryError):
        query_graph(edges, ("Asset", "asset-a"), nodes=nodes, direction="sideways")
    with pytest.raises(GraphQueryError):
        query_graph(edges, ("Asset", "asset-a"), nodes=nodes, max_depth=13)
    with pytest.raises(GraphQueryError):
        query_graph(edges, ("Asset", "asset-a"), nodes=nodes, max_nodes=0)


def test_empty_result_is_root_only():
    result = query_graph([], ("Asset", "isolated"))
    assert _keys(result) == {("Asset", "isolated")}
    assert result.edges == ()


def test_node_limit_is_enforced():
    edges, nodes = _fixture()
    result = query_graph(edges, ("Source", "source-1"), nodes=nodes, max_nodes=2)
    assert len(result.nodes) == 2
    assert result.truncated is True
    assert result.truncation_reason == "max_nodes"


def test_output_edges_always_have_returned_endpoints():
    edges, nodes = _fixture()
    result = query_graph(edges, ("Asset", "asset-a"), nodes=nodes, max_depth=3)
    keys = _keys(result)
    assert all((edge.source_kind, edge.source_id) in keys for edge in result.edges)
    assert all((edge.target_kind, edge.target_id) in keys for edge in result.edges)


def test_storage_and_contract_edge_shapes_are_both_accepted():
    result = query_graph(
        [
            {
                "source_kind": "Source",
                "source_id": "s",
                "target_kind": "Asset",
                "target_id": "a",
                "relation": "provides",
            }
        ],
        ("Source", "s"),
        direction="downstream",
        max_depth=1,
    )
    assert _keys(result) == {("Source", "s"), ("Asset", "a")}
