"""Build reviewable response proposals from generated files, never HTTP fallbacks."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from corpusflow.modules.training_center.generation import (
    KINDS,
    SOURCE_KINDS,
    SPLITS,
    UNITS,
    Json,
    json_bytes,
    ref,
    sha256,
)

FORMATS = ("pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl", "other")


def read_catalog(directory: Path) -> tuple[Json, dict[str, list[Json]]]:
    """Require a complete, hash-verified catalog; missing/corrupt files fail closed."""
    manifest: Json = json.loads((directory / "manifest.json").read_bytes())
    core = {k: v for k, v in manifest.items() if k not in {"revision", "generated_at"}}
    if sha256(json_bytes(core)) != manifest["revision"]:
        raise ValueError("manifest revision mismatch")
    rows: dict[str, list[Json]] = {}
    seen: set[str] = set()
    for entry in manifest["content_files"]:
        name = entry["path"]
        path = (directory / name).resolve()
        if name in seen or not path.is_relative_to(directory.resolve()):
            raise ValueError("invalid or duplicate content path")
        seen.add(name)
        value = path.read_bytes()
        if (
            sha256(value) != entry["sha256"]
            or len(value.splitlines()) != entry["line_count"]
            or len(value) != entry["size_bytes"]
        ):
            raise ValueError(f"content integrity mismatch: {name}")
        if name.endswith(".jsonl"):
            rows[name] = [json.loads(line) for line in value.splitlines()]
    required = {
        "sources.jsonl",
        "files.jsonl",
        "segments.jsonl",
        "datasets.jsonl",
        "processing-runs.jsonl",
        "lineage-edges.jsonl",
    }
    required.update(f"datasets/{kind}.jsonl" for kind in KINDS)
    if not required.issubset(rows):
        raise ValueError("catalog is missing required files")
    return manifest, rows


def distribution(values: list[str], keys: tuple[str, ...], measure: str, unit: str) -> Json:
    counts = Counter(value if value in keys else "unknown" for value in values)
    return {
        "measure": measure,
        "unit": unit,
        "total_count": len(values),
        "buckets": [
            {
                "key": key,
                "label": key,
                "count": counts[key],
                "ratio": counts[key] / len(values) if values else None,
            }
            for key in (*keys, "unknown")
        ],
    }


def metric(value: int | None, unit: str) -> Json:
    return {"value": value, "unit": unit}


def page(scope: Json, rows: list[Json], offset: int = 0, limit: int = 20) -> Json:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("offset >= 0 and 1 <= limit <= 100 required")
    # Sample sequence is primary; file names are primary; UUID breaks ties.
    ordered = sorted(
        rows, key=lambda row: (row.get("sequence", row.get("filename", "")), row["id"])
    )
    return {
        "scope": scope,
        "items": ordered[offset : offset + limit],
        "total_count": len(rows),
        "offset": offset,
        "limit": limit,
    }


def flow(
    label: str, files: list[Json], segments: list[Json], samples: dict[str, list[Json]]
) -> Json:
    return {
        "scope_label": label,
        "stages": [
            {"key": "files", "label": "文件", "count": len(files), "unit": "file"},
            {"key": "segments", "label": "片段", "count": len(segments), "unit": "segment"},
            *[
                {
                    "key": kind,
                    "label": kind.upper(),
                    "count": len(samples[kind]),
                    "unit": UNITS[kind],
                }
                for kind in KINDS
            ],
        ],
        "transitions": [],  # No executed parsing/processing steps to assert.
    }


def lengths(samples: list[Json], unit: str, measure: str) -> Json:
    keys = ("0-127", "128-255", "256+")
    values = [
        keys[0] if s["char_count"] < 128 else keys[1] if s["char_count"] < 256 else keys[2]
        for s in samples
    ]
    return distribution(values, keys, measure, unit)


def build_responses(directory: Path) -> Json:
    manifest, rows = read_catalog(directory)
    scope = {
        "workspace_id": manifest["workspace_id"],
        "catalog": "generated",
        "revision": manifest["revision"],
        "as_of": manifest["generated_at"],
        "metric_definition_version": "training-center.metrics.proposal.v1",
    }
    files = rows["files.jsonl"]
    segments = rows["segments.jsonl"]
    samples = {kind: rows[f"datasets/{kind}.jsonl"] for kind in KINDS}
    sources = {source["id"]: source for source in rows["sources.jsonl"]}
    datasets: list[Json] = []
    for raw in rows["datasets.jsonl"]:
        kind = raw["kind"]
        selected = samples[kind]
        # Recompute quantities from records, not manifest/summary count caches.
        datasets.append(
            {
                **raw,
                "record_count": len(selected),
                "source_refs": [
                    ref("source", sid)
                    for sid in sorted({r["id"] for s in selected for r in s["source_refs"]})
                ],
                "split_counts": {s: sum(r["split"] == s for r in selected) for s in SPLITS},
            }
        )
    overview = {
        "scope": scope,
        "metrics": {
            "file_count": metric(len(files), "file"),
            "segment_count": metric(len(segments), "segment"),
            "training_record_count": metric(sum(map(len, samples.values())), "record"),
            "token_count": metric(None, "token"),
            "quality_pass_rate": {"value": None, "unit": "ratio", "delta": None},
        },
        "formats": [
            {"format": fmt, "file_count": sum(f["format"] == fmt for f in files), "unit": "file"}
            for fmt in FORMATS
        ],
        "datasets": datasets,
        "flow": flow("generated catalog: all files and training records", files, segments, samples),
        "recent_activities": [],
    }
    selected_files = [f for f in files if f["format"] == "txt"]
    source_ids = {f["source_ref"]["id"] for f in selected_files}
    selected_samples = {
        kind: [s for s in items if any(r["id"] in source_ids for r in s["source_refs"])]
        for kind, items in samples.items()
    }
    # No generated segments in v1. Do not reinterpret training records as segments.
    selected_segments = [
        s for s in segments if s["file_ref"]["id"] in {f["id"] for f in selected_files}
    ]
    dataset_refs = sorted({r["id"] for f in selected_files for r in f["dataset_refs"]})
    stats = {
        "scope": scope,
        "metrics": {
            "file_count": metric(len(selected_files), "file"),
            "segment_count": metric(len(selected_segments), "segment"),
            "size_bytes": metric(sum(f["size_bytes"] for f in selected_files), "byte"),
            "token_count": metric(None, "token"),
            "quality_pass_rate": {"value": None, "unit": "ratio", "delta": None},
        },
        "flow": flow(
            "format=txt; linked records via source_ref",
            selected_files,
            selected_segments,
            selected_samples,
        ),
        "ingestion_trend": None,
        "availability": {
            "ingestion_trend": "ingested_at_missing" if selected_files else "no_files"
        },
        "length_distribution": lengths(selected_segments, "segment", "segment_char_length"),
        "language_distribution": distribution(
            [s["language"] for s in selected_segments], ("zh", "en"), "segment_language", "segment"
        ),
        "source_distribution": distribution(
            [f["source_kind"] for f in selected_files], SOURCE_KINDS, "file_source_kind", "file"
        ),
        "dataset_refs": [ref("dataset_version", version_id) for version_id in dataset_refs],
    }
    responses: Json = {}

    def add(name: str, path: str, body: Json, **params: Any) -> None:
        responses[name] = {
            "request": {
                "method": "GET",
                "path": f"/api/v1/training-center{path}",
                "query": {"catalog": "generated", "revision": scope["revision"], **params},
            },
            "status_code": 200,
            "body": body,
        }

    add("overview", "/overview", overview)
    add("txt_stats", "/formats/txt/stats", stats, timezone="UTC")
    # relative_path is internal catalog metadata, never an API field.
    public_files = [{k: v for k, v in f.items() if k != "relative_path"} for f in selected_files]
    add("files", "/files", page(scope, public_files), format="txt", offset=0, limit=20)
    for dataset in datasets:
        kind = dataset["kind"]
        selected = samples[kind]
        base = f"/datasets/{dataset['id']}"
        body = {
            "scope": scope,
            "dataset": dataset,
            "split_counts": dataset["split_counts"],
            "source_distribution": distribution(
                [sources[s["source_refs"][0]["id"]]["kind"] for s in selected],
                SOURCE_KINDS,
                "training_record_primary_source_kind",
                UNITS[kind],
            ),
            "destination_counts": [
                {"key": split, "count": dataset["split_counts"][split], "unit": UNITS[kind]}
                for split in SPLITS
            ],
            "length_distribution": lengths(selected, UNITS[kind], "training_record_char_length"),
            "language_distribution": distribution(
                [s["language"] for s in selected],
                ("zh", "en"),
                "training_record_language",
                UNITS[kind],
            ),
            "lineage_root_ref": ref("dataset_version", dataset["version_id"]),
        }
        add(f"{kind}_overview", f"{base}/overview", body, version=dataset["version"])
        add(
            f"{kind}_samples",
            f"{base}/samples",
            page(scope, selected),
            version=dataset["version"],
            offset=0,
            limit=20,
        )
    add(
        "cpt_samples_next",
        f"/datasets/{datasets[0]['id']}/samples",
        page(scope, samples["cpt"], offset=20),
        version="1",
        offset=20,
        limit=20,
    )
    return {
        "proposal_version": "agent2.m0.v1",
        "provenance": {
            key: manifest[key]
            for key in (
                "schema_version",
                "generator",
                "seed",
                "generation_config",
                "workspace_id",
                "revision",
                "generated_at",
            )
        },
        "responses": responses,
    }


def error_responses(normal: Json) -> Json:
    result: Json = {"proposal_version": "agent2.m0.v1", "responses": {}}
    for name, response in normal["responses"].items():
        result["responses"][name] = {
            "request": response["request"],
            "status_code": 409,
            "body": {
                "error": {
                    "code": "SNAPSHOT_EXPIRED",
                    "message": "快照已过期，请重新加载。",
                    "details": [],
                    "retryable": False,
                },
                "request_id": "example-request-001",
            },
        }
    for code, status, message in (
        ("PERMISSION_DENIED", 403, "无权访问当前工作空间。"),
        ("NOT_FOUND", 404, "对象不存在。"),
        ("VALIDATION_FAILED", 422, "分页参数不合法。"),
    ):
        result["responses"][code.lower()] = {
            "status_code": status,
            "body": {
                "error": {"code": code, "message": message, "details": [], "retryable": False},
                "request_id": "example-request-002",
            },
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-dir", type=Path, required=True)
    parser.add_argument("--empty-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new directory for normal.json, empty.json and errors.json",
    )
    args = parser.parse_args()
    normal = build_responses(args.normal_dir)
    empty = build_responses(args.empty_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, body in (("normal", normal), ("empty", empty), ("errors", error_responses(normal))):
        value = json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        (args.output_dir / f"{name}.json").write_bytes(value.encode("utf-8"))


if __name__ == "__main__":
    main()
