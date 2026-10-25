"""Compare fresh real RAG results with the committed P1-D baseline, including failures."""

import json
from pathlib import Path


def verify(baseline: dict, actual: dict) -> dict:
    old = baseline["experiments"]
    new = actual["benchmarks"]
    assert len(old) == len(new) == 6
    assert len({e["report"]["suite_sha256"] for e in new}) == 1
    for expected, measured in zip(old, new, strict=True):
        report = measured["report"]
        assert report["case_count"] == 31
        assert report["strategy"] == expected["strategy"]
        for metric in ("recall", "precision", "mrr", "ndcg", "hit", "no_answer_correct"):
            a, b = expected["metrics"][metric], report["metrics"][metric]
            assert a["denominator"] == b["denominator"]
            assert abs(a["value"] - b["value"]) < 1e-12, (metric, a, b)
    assert new[1]["report"]["metrics"]["no_answer_correct"]["value"] == 0.75
    return {
        "status": "PASS",
        "experiments": 6,
        "queries_per_experiment": 31,
        "negative_no_answer_rate_retained": 0.25,
        "latency_comparison": "NOT_ASSERTED: environment dependent",
        "annotation_status": actual["annotation_status"],
    }


if __name__ == "__main__":
    result = verify(
        json.loads(Path("docs/reports/P1-D_EVIDENCE.json").read_text()),
        json.loads(Path(".local/p1d/evidence.json").read_text()),
    )
    Path(".local/p2/p1-reproducibility.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
