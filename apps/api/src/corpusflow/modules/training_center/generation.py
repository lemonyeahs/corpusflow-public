"""Deterministic, dependency-free generated catalog. No database or network I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

GENERATOR_VERSION = "1.0.0"
SCHEMA_VERSION = "training-center.generated.v1"
KINDS = ("cpt", "sft", "dpo")
SPLITS = ("train", "validation", "test")
SOURCE_KINDS = ("web", "book", "paper")
UNITS = {"cpt": "article", "sft": "record", "dpo": "pair"}
PRODUCT_TYPES = {"cpt": "pretrain", "sft": "sft", "dpo": "dpo"}
TOPICS = (
    ("来源追溯", "保留来源标识与内容版本，便于检查记录之间的关联。"),
    ("分组切分", "同一来源组只属于一个集合，切分后再检查重复内容。"),
    ("字符规范", "统一字符前应保留原文，完成后检查语义和标点是否完整。"),
    ("质量评估", "固定评估口径，分别记录有效内容、缺失字段与待复核项。"),
    ("隐私保护", "识别敏感字段后使用占位符，并检查上下文是否仍然可用。"),
    ("版本管理", "为每个不可变版本保留配置与内容哈希，避免混合不同快照。"),
)
Json = dict[str, Any]


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def ref(object_type: str, object_id: str) -> Json:
    return {"catalog": "generated", "type": object_type, "id": object_id}


def split_targets(count: int) -> dict[str, int]:
    """Largest remainders, with ties resolved train, validation, test (integer math)."""
    if type(count) is not int or count < 0:
        raise ValueError("count must be a non-negative integer")
    weights = (90, 5, 5)
    targets = [count * weight // 100 for weight in weights]
    order = sorted(range(3), key=lambda i: (-(count * weights[i] % 100), i))
    for index in order[: count - sum(targets)]:
        targets[index] += 1
    return dict(zip(SPLITS, targets, strict=True))


def validate_config(workspace_id: str, seed: int, counts: Json) -> None:
    # IDs become path components. Reject Windows device names as well as traversal.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", workspace_id):
        raise ValueError("workspace-id must be 1-64 ASCII letters, digits, underscores or hyphens")
    if re.fullmatch(r"(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])", workspace_id):
        raise ValueError("workspace-id cannot be a reserved device name")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    for count in counts.values():
        split_targets(count)


def build_catalog(
    workspace_id: str,
    seed: int = 42,
    cpt_count: int = 2000,
    sft_count: int = 1500,
    dpo_count: int = 800,
    *,
    max_source_group_size: int = 5,
) -> tuple[Json, dict[str, bytes]]:
    """Build immutable bytes; runtime timestamps and output paths never affect them."""
    counts = dict(zip(KINDS, (cpt_count, sft_count, dpo_count), strict=True))
    validate_config(workspace_id, seed, counts)
    if type(max_source_group_size) is not int or not 1 <= max_source_group_size <= 1000:
        raise ValueError("max-source-group-size must be an integer between 1 and 1000")
    config: Json = {
        "counts": counts,
        "max_source_group_size": max_source_group_size,
        "language": "zh",
    }
    identity = {
        "workspace_id": workspace_id,
        "seed": seed,
        "config": config,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    namespace = uuid5(NAMESPACE_URL, json_bytes(identity).decode("utf-8"))

    def stable_id(key: str) -> str:
        return str(uuid5(namespace, key))

    rng = random.Random(seed)
    data: dict[str, list[Json]] = {
        name: []
        for name in (
            "sources.jsonl",
            "files.jsonl",
            "segments.jsonl",
            "processing-runs.jsonl",
            "lineage-edges.jsonl",
            "datasets.jsonl",
        )
    }
    content: dict[str, bytes] = {}
    for kind, count in counts.items():
        dataset_id = stable_id(f"dataset:{kind}")
        version_id = stable_id(f"dataset-version:{kind}:1")
        samples: list[Json] = []
        source_refs: list[Json] = []
        targets = split_targets(count)
        sequence = 0
        group_sequence = 0
        for split, target in targets.items():
            remaining = target
            while remaining:
                # Groups are CREATED within a planned split, never divided afterwards.
                group_size = min(config["max_source_group_size"], remaining)
                group_sequence += 1
                group_id = stable_id(f"group:{kind}:{group_sequence}")
                source_id = stable_id(f"source:{kind}:{group_sequence}")
                file_id = stable_id(f"file:{kind}:{group_sequence}")
                source_kind = rng.choice(SOURCE_KINDS)
                topic, explanation = rng.choice(TOPICS)
                source_ref = ref("source", source_id)
                source_refs.append(source_ref)
                source_text = (
                    f"{topic}\n来源组 {group_sequence}，数据类型 {kind}。\n{explanation}\n"
                    "这是本地模板生成的通用类别内容，不代表真实出版物或已执行的处理任务。\n"
                )
                path = f"source-files/{file_id}.txt"
                content[path] = source_text.encode("utf-8")
                data["sources.jsonl"].append(
                    {
                        "id": source_id,
                        "workspace_id": workspace_id,
                        "kind": source_kind,
                        "source_group_id": group_id,
                        "split": split,
                        "title": topic,
                        "origin": "generated_template",
                        "author": None,
                        "url": None,
                        "license": None,
                    }
                )
                data["files.jsonl"].append(
                    {
                        "id": file_id,
                        "workspace_id": workspace_id,
                        "filename": f"{file_id}.txt",
                        "relative_path": path,
                        "format": "txt",
                        "media_type": "text/plain",
                        "language": "zh",
                        "size_bytes": len(content[path]),
                        "source_ref": source_ref,
                        "source_kind": source_kind,
                        "ingested_at": None,
                        "processing_status": "unprocessed",
                        "segment_count": 0,
                        "dataset_refs": [ref("dataset_version", version_id)],
                    }
                )
                for within_group in range(group_size):
                    sequence += 1
                    prompt = (
                        f"关于{topic}，第 {group_sequence} 组情境 {within_group + 1} 应注意什么？"
                    )
                    answer = f"{explanation}建议记录检查依据，并对不确定内容安排复核。"
                    payload: Json
                    if kind == "cpt":
                        payload = {"title": topic, "text": f"{prompt}\n\n{answer}"}
                        char_count = len(payload["text"])
                    elif kind == "sft":
                        messages = [
                            {"role": "system", "content": "请给出具体建议，并说明需要核验的内容。"},
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": answer},
                            {"role": "user", "content": "如果缺少检查依据呢？"},
                            {
                                "role": "assistant",
                                "content": "标记为待核验，不能推断已经通过检查。",
                            },
                        ]
                        payload = {"messages": messages}
                        char_count = sum(len(message["content"]) for message in messages)
                    else:
                        payload = {
                            "prompt": prompt,
                            "chosen": answer,
                            "rejected": "无需检查依据，直接认为所有记录都已经通过。",
                            "preference_reason": "优选回答给出可核验步骤，避免无依据的成功判断。",
                        }
                        char_count = sum(
                            len(payload[key]) for key in ("prompt", "chosen", "rejected")
                        )
                    samples.append(
                        {
                            "id": stable_id(f"sample:{kind}:{sequence}"),
                            "workspace_id": workspace_id,
                            "kind": kind,
                            "dataset_id": dataset_id,
                            "dataset_version": "1",
                            "sequence": sequence,
                            "split": split,
                            "source_group_id": group_id,
                            "source_refs": [source_ref],
                            "segment_refs": [],
                            "language": "zh",
                            "char_count": char_count,
                            "token_count": None,
                            "token_count_method": None,
                            **payload,
                        }
                    )
                remaining -= group_size
        data[f"datasets/{kind}.jsonl"] = samples
        data["datasets.jsonl"].append(
            {
                "id": dataset_id,
                "workspace_id": workspace_id,
                "version": "1",
                "version_id": version_id,
                "kind": kind,
                "product_type": PRODUCT_TYPES[kind],
                "name": f"{kind.upper()} 训练数据",
                "record_count": len(samples),
                "record_unit": UNITS[kind],
                "split_counts": {
                    split: sum(s["split"] == split for s in samples) for split in SPLITS
                },
                "token_count": None,
                "token_count_method": None,
                "status": "available",
                "source_refs": source_refs,
            }
        )
    for path, rows in data.items():
        content[path] = b"".join(json_bytes(row) for row in rows)
    files = [
        {
            "path": path,
            "sha256": sha256(value),
            "line_count": len(value.splitlines()),
            "size_bytes": len(value),
        }
        for path, value in sorted(content.items())
    ]
    manifest: Json = {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "generator": {"path": "scripts/generate_training_center.py", "version": GENERATOR_VERSION},
        "seed": seed,
        "generation_config": config,
        "content_files": files,
        "counts": {
            "files": len(data["files.jsonl"]),
            "sources": len(data["sources.jsonl"]),
            "segments": len(data["segments.jsonl"]),
            "datasets": {
                row["kind"]: {
                    "record_count": row["record_count"],
                    "record_unit": row["record_unit"],
                    "split_counts": row["split_counts"],
                }
                for row in data["datasets.jsonl"]
            },
            "source_kinds": dict(
                sorted(Counter(row["kind"] for row in data["sources.jsonl"]).items())
            ),
        },
        "split_policy": {
            "name": "planned-source-groups-v1",
            "weights": dict(zip(SPLITS, (90, 5, 5), strict=True)),
            "rounding": "largest_remainder; ties: train, validation, test",
            "grouping": (
                "create groups of at most 5 within split budgets; never split an existing group"
            ),
            "scope": "source_group_id is unique across all dataset kinds in this catalog",
        },
        "provenance": {
            "origin": "generated_template",
            "external_services": [],
            "source_categories": list(SOURCE_KINDS),
            "real_source_claims": False,
            "processing_executed": False,
            "missing_entities": ["segment", "operator_run"],
            "purpose": "development catalog; no real author, URL, dataset or license claims",
            "char_count_method": (
                "unicode_codepoints; CPT text, SFT message contents, DPO prompt+chosen+rejected"
            ),
        },
    }
    manifest["revision"] = sha256(json_bytes(manifest))
    return manifest, content


def write_catalog(output_dir: Path, manifest: Json, content: dict[str, bytes]) -> Path:
    """Exclusive directory creation. Manifest is the commit marker, written last.

    An interrupted directory is incomplete and must never be served. We retain it
    for diagnosis and never overwrite/reuse it, even if it is empty.
    """
    output_dir.mkdir(parents=True, exist_ok=False)
    for path, value in content.items():
        destination = output_dir / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(value)
    stamped = {**manifest, "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    temporary = output_dir / "manifest.json.tmp"
    with temporary.open("xb") as stream:
        stream.write(json_bytes(stamped))
    temporary.rename(output_dir / "manifest.json")
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-source-group-size", type=int, default=5)
    parser.add_argument(
        "--output-dir", type=Path, help="new final directory under .local/training-center"
    )
    for kind, count in zip(KINDS, (2000, 1500, 800), strict=True):
        parser.add_argument(f"--{kind}-count", type=int, default=count)
    args = parser.parse_args(argv)
    try:
        manifest, content = build_catalog(
            args.workspace_id,
            args.seed,
            args.cpt_count,
            args.sft_count,
            args.dpo_count,
            max_source_group_size=args.max_source_group_size,
        )
        root = Path(__file__).resolve().parents[6] / ".local/training-center"
        output = (args.output_dir or root / args.workspace_id / manifest["revision"]).resolve()
        if not output.is_relative_to(root.resolve()) or output == root.resolve():
            raise ValueError("output-dir must be a new directory inside .local/training-center")
        write_catalog(output, manifest, content)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"generation failed: {exc}\n")
    print(
        json.dumps(
            {
                "output_dir": str(output),
                "revision": manifest["revision"],
                "counts": manifest["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0
