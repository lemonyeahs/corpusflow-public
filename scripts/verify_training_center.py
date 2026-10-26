"""Run the Agent 4 lineage fixture checks and optionally probe the real API.

The fixture checks are deterministic graph semantics. They are useful before the
shared router exists, but they do not count as real workspace lineage acceptance.
Pass ``--base-url`` only after the D router and a disposable authenticated
workspace are available; live checks remain explicitly reported as NOT RUN here
until those credentials and IDs are supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "apps/api" / "src"))

from corpusflow.modules.lineage_graph import query_graph  # noqa: E402

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "lineage_graph_fixture.json"


def _keys(result):
    return {(node.kind, node.id) for node in result.nodes}


def run_fixture() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    edges = payload["edges"]
    nodes = payload["nodes"]
    cases: list[dict[str, object]] = []

    def case(case_id: str, result, expected_nodes: set[tuple[str, str]], **expected):
        actual = _keys(result)
        passed = actual == expected_nodes
        for key, value in expected.items():
            passed = passed and getattr(result, key) == value
        cases.append(
            {
                "id": case_id,
                "status": "PASS" if passed else "FAIL",
                "expected_nodes": sorted(expected_nodes),
                "actual_nodes": sorted(actual),
                **expected,
            }
        )
        if not passed:
            raise AssertionError(cases[-1])

    case(
        "A-raw-asset-downstream",
        query_graph(edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=2),
        {
            ("Asset", "asset-a"),
            ("PipelineRun", "run-1"),
            ("DocumentVersion", "doc-v1"),
            ("Asset", "asset-b"),
        },
    )
    case(
        "B-dataset-upstream",
        query_graph(
            edges, ("DatasetVersion", "dataset-v1"), nodes=nodes, direction="upstream", max_depth=6
        ),
        {
            ("DatasetVersion", "dataset-v1"),
            ("CandidateSample", "sample-1"),
            ("Segment", "segment-1"),
            ("Segment", "segment-2"),
            ("DocumentVersion", "doc-v1"),
            ("PipelineRun", "run-1"),
            ("Asset", "asset-a"),
            ("Source", "source-1"),
        },
    )
    case(
        "C-depth-boundary",
        query_graph(edges, ("Asset", "asset-a"), nodes=nodes, direction="downstream", max_depth=1),
        {("Asset", "asset-a"), ("Asset", "asset-b"), ("PipelineRun", "run-1")},
        truncated=True,
        truncation_reason="max_depth",
    )
    case(
        "E-node-boundary",
        query_graph(edges, ("Source", "source-1"), nodes=nodes, max_nodes=2),
        {("Source", "source-1"), ("Asset", "asset-a")},
        truncated=True,
        truncation_reason="max_nodes",
    )
    return {"status": "PASS", "fixture": str(FIXTURE), "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url", help="Reserved for live API checks; requires auth fixture IDs"
    )
    args = parser.parse_args()
    result = run_fixture()
    result["live_api"] = {
        "status": "NOT RUN",
        "reason": (
            "lineage graph router, authenticated workspace fixture, and stable root IDs "
            "are not available in this baseline"
        ),
        "base_url": args.base_url,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
