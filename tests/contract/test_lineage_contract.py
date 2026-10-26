import json
from pathlib import Path


def test_lineage_fixture_has_contract_safe_edges_and_endpoints():
    payload = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "lineage_graph_fixture.json").read_text(
            encoding="utf-8"
        )
    )
    node_keys = {(node["kind"], node["id"]) for node in payload["nodes"]}
    assert payload["scope"]["catalog"] in {"generated", "workspace"}
    assert payload["root"] in [
        {"kind": node["kind"], "id": node["id"]} for node in payload["nodes"]
    ]
    edge_keys = set()
    for edge in payload["edges"]:
        source = (edge["from_type"], edge["from_id"])
        target = (edge["to_type"], edge["to_id"])
        assert source in node_keys
        assert target in node_keys
        edge_keys.add((*source, *target, edge["relation"]))
    assert len(edge_keys) == len(payload["edges"])
