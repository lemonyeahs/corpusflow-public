from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from corpusflow.modules.training_center.generation import (
    KINDS,
    SPLITS,
    build_catalog,
    split_targets,
    write_catalog,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/generate_training_center.py"


def records(content, name):
    return [json.loads(line) for line in content[name].splitlines()]


def test_large_source_groups_preserve_exact_splits_and_reproducibility():
    args = ("large-groups", 42, 101, 0, 0)
    manifest, content = build_catalog(*args, max_source_group_size=50)
    assert (manifest, content) == build_catalog(*args, max_source_group_size=50)
    assert manifest["generation_config"]["max_source_group_size"] == 50
    samples = records(content, "datasets/cpt.jsonl")
    assert Counter(row["split"] for row in samples) == split_targets(101)
    groups = defaultdict(set)
    for row in samples:
        groups[row["source_group_id"]].add(row["split"])
    assert len(groups) == 4
    assert all(len(splits) == 1 for splits in groups.values())
    assert build_catalog(*args)[0]["revision"] != manifest["revision"]


@pytest.mark.parametrize("size", [0, 1001, True, 2.5])
def test_source_group_size_is_bounded(size):
    with pytest.raises(ValueError, match="max-source-group-size"):
        build_catalog("invalid-group", max_source_group_size=size)


@pytest.fixture(scope="module")
def default_catalog():
    return build_catalog("test-workspace")


def test_reproducibility_and_local_rng(default_catalog, tmp_path):
    manifest, content = default_catalog
    state = random.getstate()
    again, again_content = build_catalog("test-workspace")
    assert random.getstate() == state
    assert (manifest, content) == (again, again_content)
    random.seed(910)
    try:
        assert build_catalog("test-workspace") == default_catalog
    finally:
        random.setstate(state)
    first = write_catalog(tmp_path / "first", manifest, content)
    second = write_catalog(tmp_path / "second", again, again_content)
    left = json.loads((first / "manifest.json").read_bytes())
    right = json.loads((second / "manifest.json").read_bytes())
    assert left.pop("generated_at").endswith("Z")
    assert right.pop("generated_at").endswith("Z")
    assert left == right == manifest
    for name in content:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_configuration_and_workspace_change_identity():
    args = {"workspace_id": "one", "seed": 1, "cpt_count": 2, "sft_count": 0, "dpo_count": 0}
    baseline = build_catalog(**args)
    for change in ({"workspace_id": "two"}, {"seed": 2}, {"cpt_count": 3}):
        other = build_catalog(**(args | change))
        assert baseline[0]["revision"] != other[0]["revision"]
        ids = {s["id"] for s in records(baseline[1], "datasets/cpt.jsonl")}
        assert ids.isdisjoint(s["id"] for s in records(other[1], "datasets/cpt.jsonl"))


def test_default_counts_and_splits(default_catalog):
    manifest, content = default_catalog
    for kind, expected in zip(
        KINDS, ((1800, 100, 100), (1350, 75, 75), (720, 40, 40)), strict=True
    ):
        rows = records(content, f"datasets/{kind}.jsonl")
        actual = Counter(row["split"] for row in rows)
        assert tuple(actual[split] for split in SPLITS) == expected
        assert len(rows) == sum(expected)
        assert manifest["counts"]["datasets"][kind]["record_count"] == len(rows)
    assert manifest["counts"]["files"] == len(records(content, "files.jsonl")) == 860


def test_all_references_and_groups_resolve(default_catalog):
    manifest, content = default_catalog
    sources = {s["id"]: s for s in records(content, "sources.jsonl")}
    files = records(content, "files.jsonl")
    datasets = {d["id"]: d for d in records(content, "datasets.jsonl")}
    registry = {
        "source": set(sources),
        "file": {f["id"] for f in files},
        "segment": set(),
        "dataset_version": {d["version_id"] for d in datasets.values()},
    }
    group_splits = defaultdict(set)
    group_sizes = Counter()
    all_ids = set()
    for kind in KINDS:
        for row in records(content, f"datasets/{kind}.jsonl"):
            assert row["id"] not in all_ids
            all_ids.add(row["id"])
            assert row["workspace_id"] == manifest["workspace_id"]
            assert row["dataset_id"] in datasets
            assert row["dataset_version"] == datasets[row["dataset_id"]]["version"]
            group_splits[row["source_group_id"]].add(row["split"])
            group_sizes[row["source_group_id"]] += 1
            for reference in row["source_refs"] + row["segment_refs"]:
                assert reference["catalog"] == "generated"
                assert reference["id"] in registry[reference["type"]]
            assert row["source_refs"]
            source = sources[row["source_refs"][0]["id"]]
            assert source["source_group_id"] == row["source_group_id"]
            assert source["split"] == row["split"]
    assert all(len(splits) == 1 for splits in group_splits.values())
    assert max(group_sizes.values()) == 5  # Exercise multi-record groups, not just singleton IDs.
    assert set(group_sizes) == {s["source_group_id"] for s in sources.values()}
    for file in files:
        assert file["source_ref"]["id"] in sources
        assert file["size_bytes"] == len(content[file["relative_path"]])
        assert file["processing_status"] == "unprocessed"
        assert file["segment_count"] == 0 and file["ingested_at"] is None
        for reference in file["dataset_refs"]:
            assert reference["id"] in registry[reference["type"]]
    for dataset in datasets.values():
        for reference in dataset["source_refs"]:
            assert reference["id"] in sources
    for source in sources.values():
        assert source["kind"] in {"web", "book", "paper"}
        assert source["author"] is source["url"] is source["license"] is None
    for name in ("segments.jsonl", "processing-runs.jsonl", "lineage-edges.jsonl"):
        assert content[name] == b""


def test_record_shapes_and_character_units(default_catalog):
    _, content = default_catalog
    for kind in KINDS:
        for row in records(content, f"datasets/{kind}.jsonl"):
            assert row["kind"] == kind
            assert row["token_count"] is row["token_count_method"] is None
            assert row["segment_refs"] == []
            if kind == "cpt":
                assert isinstance(row["text"], str) and row["text"]
                assert "messages" not in row and "chosen" not in row
                expected_chars = len(row["text"])
            elif kind == "sft":
                assert [m["role"] for m in row["messages"]] == [
                    "system",
                    "user",
                    "assistant",
                    "user",
                    "assistant",
                ]
                assert all(isinstance(m["content"], str) and m["content"] for m in row["messages"])
                expected_chars = sum(len(m["content"]) for m in row["messages"])
            else:
                assert all(
                    isinstance(row[k], str) and row[k] for k in ("prompt", "chosen", "rejected")
                )
                assert row["chosen"] != row["rejected"]
                expected_chars = sum(len(row[k]) for k in ("prompt", "chosen", "rejected"))
            assert row["char_count"] == expected_chars
    assert {d["kind"]: d["product_type"] for d in records(content, "datasets.jsonl")} == {
        "cpt": "pretrain",
        "sft": "sft",
        "dpo": "dpo",
    }


def test_manifest_matches_disk_and_revision(default_catalog, tmp_path):
    manifest, content = default_catalog
    output = write_catalog(tmp_path / "catalog", manifest, content)
    entries = manifest["content_files"]
    assert len(entries) == len({entry["path"] for entry in entries})
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == {
        "manifest.json",
        *(entry["path"] for entry in entries),
    }
    for entry in entries:
        value = (output / entry["path"]).read_bytes()
        assert hashlib.sha256(value).hexdigest() == entry["sha256"]
        assert len(value.splitlines()) == entry["line_count"]
        assert len(value) == entry["size_bytes"]
    core = {k: v for k, v in manifest.items() if k != "revision"}
    serialized = (
        json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assert hashlib.sha256(serialized).hexdigest() == manifest["revision"]
    assert manifest["provenance"]["processing_executed"] is False


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, (0, 0, 0)),
        (1, (1, 0, 0)),
        (2, (2, 0, 0)),
        (7, (6, 1, 0)),
        (10, (9, 1, 0)),
        (11, (10, 1, 0)),
        (19, (17, 1, 1)),
        (23, (21, 1, 1)),
    ],
)
def test_small_rounding_and_generation(count, expected):
    assert tuple(split_targets(count).values()) == expected
    _, content = build_catalog("small", cpt_count=count, sft_count=count, dpo_count=count)
    groups = defaultdict(set)
    for kind in KINDS:
        rows = records(content, f"datasets/{kind}.jsonl")
        assert len(rows) == count
        counts = Counter(row["split"] for row in rows)
        assert tuple(counts[s] for s in SPLITS) == expected
        for row in rows:
            groups[row["source_group_id"]].add(row["split"])
    assert all(len(splits) == 1 for splits in groups.values())
    if count == 0:
        assert content["sources.jsonl"] == content["files.jsonl"] == b""


@pytest.mark.parametrize("count", [-1, 1.5, True, "2"])
def test_invalid_counts(count):
    with pytest.raises(ValueError):
        build_catalog("test", cpt_count=count)


@pytest.mark.parametrize(
    "workspace", ["", "../escape", "a/b", "a\\b", "a:b", "CON", "NUL", "x" * 65]
)
def test_invalid_workspace(workspace):
    with pytest.raises(ValueError):
        build_catalog(workspace)


def test_invalid_seed():
    with pytest.raises(ValueError):
        build_catalog("test", seed=True)


@pytest.mark.parametrize("existing", ["empty", "file", "populated"])
def test_output_is_never_overwritten(tmp_path, existing):
    output = tmp_path / "existing"
    if existing == "file":
        output.write_bytes(b"preserve")
    else:
        output.mkdir()
        if existing == "populated":
            (output / "manifest.json").write_bytes(b"preserve")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    manifest, content = build_catalog("test", cpt_count=0, sft_count=0, dpo_count=0)
    with pytest.raises(FileExistsError):
        write_catalog(output, manifest, content)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "args",
    [
        ["--cpt-count", "-1"],
        ["--sft-count", "abc"],
        ["--seed", "no"],
        ["--workspace-id", "../bad"],
        ["--output-dir", "."],
    ],
)
def test_invalid_cli(args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workspace-id", "test", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert result.stderr


@pytest.fixture
def cli_output():
    local_root = (ROOT / ".local/training-center").resolve()
    local_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cli-test-", dir=local_root) as directory:
        output = Path(directory).resolve()
        assert output.is_relative_to(local_root) and output != local_root
        yield output / "cli"


def test_cli_success_and_refusal(cli_output):
    output = cli_output
    command = [
        sys.executable,
        str(SCRIPT),
        "--workspace-id",
        "cli",
        "--seed",
        "-1",
        "--cpt-count",
        "3",
        "--sft-count",
        "2",
        "--dpo-count",
        "1",
        "--output-dir",
        str(output),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    before = (output / "manifest.json").read_bytes()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert (output / "manifest.json").read_bytes() == before
