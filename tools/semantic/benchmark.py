"""Offline real model benchmark over the exact P1-D fixture. No downloads or credentials."""

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model_dir = args.model_dir.resolve()
    assert (model_dir / "model.safetensors").is_file()
    fixture = json.loads(Path("tests/fixtures/p1d/corpus.json").read_text())
    model = SentenceTransformer(str(model_dir), local_files_only=True, device="cpu")
    docs = [f for _, f, _ in fixture["facts"]]
    suite = json.loads(Path("docs/reports/P1-D_EVIDENCE.json").read_text())["suite"]
    evidence_to_index = {}
    for case in suite["cases"]:
        if len(case["relevance"]) == 1:
            evidence_to_index[next(iter(case["relevance"]))] = docs.index(case["reference_answer"])
    started = time.monotonic()
    vectors = model.encode(docs, normalize_embeddings=True, batch_size=16)
    build_ms = (time.monotonic() - started) * 1000
    results = []
    for case in suite["cases"]:
        q = case["query"]
        start = time.monotonic()
        v = model.encode([q], normalize_embeddings=True)[0]
        scores = vectors @ v
        rank = np.argsort(-scores, kind="stable")[:3].tolist()
        expected = {evidence_to_index[sid] for sid in case["relevance"]}
        hits = expected.intersection(rank)
        results.append(
            {
                "query": q,
                "expected": sorted(expected),
                "ranks": rank,
                "scores": [float(scores[n]) for n in rank],
                "recall": len(hits) / len(expected) if expected else None,
                "precision": len(hits) / 3 if expected else None,
                "mrr": next((1 / (j + 1) for j, n in enumerate(rank) if n in expected), 0)
                if expected
                else None,
                "ndcg": sum(1 / math.log2(j + 2) for j, n in enumerate(rank) if n in expected)
                / sum(1 / math.log2(j + 2) for j in range(len(expected)))
                if expected
                else None,
                "latency_ms": (time.monotonic() - start) * 1000,
            }
        )
    report = {
        "scope": "offline component benchmark; NOT platform vector index acceptance",
        "suite_sha256": suite["sha256"],
        "model": model_dir.name,
        "model_sha256": hashlib.sha256((model_dir / "model.safetensors").read_bytes()).hexdigest(),
        "dimension": int(vectors.shape[1]),
        "build_ms": build_ms,
        "vector_bytes": int(vectors.nbytes),
        "input_sha256": hashlib.sha256(json.dumps(docs, ensure_ascii=False).encode()).hexdigest(),
        "metrics": {
            k: sum(r[k] for r in results if r[k] is not None)
            / sum(r[k] is not None for r in results)
            for k in ("recall", "precision", "mrr", "ndcg")
        },
        "no_answer_false_retrieval": sum(bool(r["ranks"]) for r in results if not r["expected"])
        / sum(not r["expected"] for r in results),
        "threshold": "none; exact top-K always returns candidates",
        "cases": results,
        "cost": "local CPU; external API calls=0; monetary cost NOT_MEASURED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
