from __future__ import annotations

import copy
import io
import json
import os
from types import SimpleNamespace

import pytest
from corpusflow.modules.training_center.catalog import (
    CatalogError,
    GeneratedCatalog,
    bounded_read,
    safe_child,
)
from corpusflow.modules.training_center.generation import (
    build_catalog,
    json_bytes,
    sha256,
    write_catalog,
)


def candidate(root, workspace="workspace-a", seed=42, counts=(23, 11, 7), mutate=None):
    manifest, content = build_catalog(workspace, seed, *counts)
    if mutate is not None:
        mutate(manifest, content)
        manifest["content_files"] = [
            {
                "path": path,
                "size_bytes": len(value),
                "sha256": sha256(value),
                "line_count": len(value.splitlines()),
            }
            for path, value in sorted(content.items())
        ]
        manifest["revision"] = sha256(
            json_bytes({k: v for k, v in manifest.items() if k != "revision"})
        )
    revision = manifest["revision"]
    path = write_catalog(root / workspace / revision, manifest, content)
    return revision, path


def test_explicit_large_catalog_budget_keeps_default_and_hard_caps(tmp_path):
    assert GeneratedCatalog(tmp_path).max_records == 100_000
    large = GeneratedCatalog(tmp_path, max_records=300_000, max_bytes=1024**3)
    assert large.max_records == 300_000
    for options in ({"max_records": 1_000_001}, {"max_bytes": 1024**3 + 1}):
        with pytest.raises(ValueError, match="catalog limits"):
            GeneratedCatalog(tmp_path, **options)


@pytest.fixture
def published(tmp_path):
    store = GeneratedCatalog(tmp_path)
    revision, path = candidate(tmp_path)
    store.publish("workspace-a", revision)
    return store, revision, path


def test_publication_is_explicit_and_atomic(tmp_path):
    store = GeneratedCatalog(tmp_path)
    first, _ = candidate(tmp_path, seed=1)
    with pytest.raises(CatalogError, match="NOT_FOUND"):
        store.load("workspace-a", first)
    store.publish("workspace-a", first)
    assert store.load("workspace-a").scope.revision == first
    second, _ = candidate(tmp_path, seed=2)
    store.publish("workspace-a", second)
    assert store.load("workspace-a").scope.revision == second
    assert store.load("workspace-a", first).scope.revision == first
    before = (tmp_path / "workspace-a/catalog.json").read_bytes()
    store.publish("workspace-a", second)
    assert (tmp_path / "workspace-a/catalog.json").read_bytes() == before
    for revision in (first, second):
        with pytest.raises(CatalogError, match="INVALID_STATE_TRANSITION"):
            store.retire("workspace-a", revision)
    third, _ = candidate(tmp_path, seed=3)
    store.publish("workspace-a", third)
    store.retire("workspace-a", first)
    with pytest.raises(CatalogError, match="SNAPSHOT_EXPIRED"):
        store.load("workspace-a", first)
    assert (tmp_path / "workspace-a" / first).exists()  # Reader never deletes data.
    assert store.load("workspace-a", second).scope.revision == second
    with pytest.raises(CatalogError, match="SNAPSHOT_EXPIRED"):
        store.publish("workspace-a", first)


def test_failed_publication_preserves_previous_pointer(published):
    store, revision, _ = published
    broken, path = candidate(store.root, seed=2)
    (path / "datasets/cpt.jsonl").write_bytes(b"broken\n")
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.publish("workspace-a", broken)
    assert store.load("workspace-a").scope.revision == revision


def test_timestamp_is_stable_after_publication(published):
    store, revision, path = published
    manifest = json.loads((path / "manifest.json").read_bytes())
    manifest["generated_at"] = "2020-01-01T00:00:00Z"
    (path / "manifest.json").write_bytes(json_bytes(manifest))
    # generated_at is excluded from revision, but a published manifest itself is immutable.
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.load("workspace-a")
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.publish("workspace-a", revision)


def test_atomic_replace_failure_preserves_registry(published, monkeypatch):
    store, revision, _ = published
    next_revision, _ = candidate(store.root, seed=2)
    registry = store.root / "workspace-a/catalog.json"
    before = registry.read_bytes()

    def interrupted(*args):
        raise OSError("test interruption before atomic replace")

    monkeypatch.setattr(os, "replace", interrupted)
    with pytest.raises(OSError, match="test interruption"):
        store.publish("workspace-a", next_revision)
    assert registry.read_bytes() == before
    assert store.load("workspace-a").scope.revision == revision
    assert not list(registry.parent.glob(".catalog-*.tmp"))


def test_oversized_registry_preserves_readable_active_revision(published):
    store, revision, _ = published
    path = store.root / "workspace-a/catalog.json"
    previous = path.read_bytes()
    registry = json.loads(previous)
    retired = [sha256(str(i).encode()) for i in range(6000)]
    registry["retired_revisions"] = retired
    registry["manifest_hashes"].update({value: value for value in retired})
    with pytest.raises(CatalogError, match="CATALOG_LIMIT_EXCEEDED"):
        store._write_registry("workspace-a", registry)
    assert path.read_bytes() == previous
    assert store.load("workspace-a").scope.revision == revision


def test_warm_cache_revalidates_content_and_does_not_expose_mutable_cache(published):
    store, revision, path = published
    snapshot = store.load("workspace-a")
    snapshot.sources.clear()
    snapshot.files[0].filename = "changed"
    assert store.load("workspace-a").sources
    assert store.load("workspace-a").files[0].filename != "changed"
    file = path / "datasets/cpt.jsonl"
    before = file.stat()
    value = bytearray(file.read_bytes())
    value[20] = 120 if value[20] != 120 else 121
    file.write_bytes(value)
    os.utime(file, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.load("workspace-a", revision)


@pytest.mark.parametrize("value", ["../workspace-b", "a/b", "a\\b", "C:escape", "/absolute", "CON"])
def test_workspace_path_rejected(tmp_path, value):
    with pytest.raises(CatalogError):
        GeneratedCatalog(tmp_path).load(value)


@pytest.mark.parametrize("value", ["../escape", "a" * 63, "g" * 64, "C:/absolute", ""])
def test_revision_path_rejected(published, value):
    with pytest.raises(CatalogError, match="INVALID_ARGUMENT"):
        published[0].load("workspace-a", value)


@pytest.mark.parametrize(
    "value", ["../escape", "./file", "a//b", "C:/file", "a\\b", "/file", "a/../b"]
)
def test_manifest_paths_rejected(tmp_path, value):
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        safe_child(tmp_path, value)


def test_workspace_and_file_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "catalogs"
    root.mkdir()
    link = root / "workspace-a"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        # Windows junctions do not require developer-mode symlink privileges.
        if os.name != "nt":
            raise
        import subprocess

        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True
        )
        assert result.returncode == 0
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        GeneratedCatalog(root).load("workspace-a")
    # Remove only the link itself; never recurse into its target.
    if link.is_symlink():
        link.unlink()
    else:
        link.rmdir()
    assert outside.exists()


def test_manifest_workspace_mismatch(published):
    store, revision, path = published
    manifest = json.loads((path / "manifest.json").read_bytes())
    manifest["workspace_id"] = "workspace-b"
    (path / "manifest.json").write_bytes(json_bytes(manifest))
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.load("workspace-a", revision)


@pytest.mark.parametrize(
    "problem", ["source", "segment", "group", "workspace", "split_count", "sequence", "chars"]
)
def test_self_consistent_hashes_do_not_hide_invalid_semantics(tmp_path, problem):
    def mutate(manifest, content):
        rows = [json.loads(line) for line in content["datasets/cpt.jsonl"].splitlines()]
        if problem == "source":
            rows[0]["source_refs"][0]["id"] = "not-a-source"
        elif problem == "segment":
            rows[0]["segment_refs"] = [{"catalog": "generated", "type": "segment", "id": "missing"}]
        elif problem == "group":
            rows[0]["source_group_id"] = "unrelated"
        elif problem == "workspace":
            rows[0]["workspace_id"] = "workspace-b"
        elif problem == "split_count":
            rows.pop()
        elif problem == "sequence":
            rows[1]["sequence"] = rows[0]["sequence"]
        else:
            rows[0]["char_count"] += 1
        content["datasets/cpt.jsonl"] = b"".join(json_bytes(row) for row in rows)

    revision, _ = candidate(tmp_path, mutate=mutate)
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        GeneratedCatalog(tmp_path).publish("workspace-a", revision)


def test_record_and_byte_limits(tmp_path):
    revision, path = candidate(tmp_path)
    for store in (
        GeneratedCatalog(tmp_path, max_records=40),
        GeneratedCatalog(tmp_path, max_bytes=1),
    ):
        with pytest.raises(CatalogError, match="CATALOG_LIMIT_EXCEEDED") as exc:
            store.verify("workspace-a", revision)
        assert exc.value.status == 413
    manifest = json.loads((path / "manifest.json").read_bytes())
    size = sum(entry["size_bytes"] for entry in manifest["content_files"])
    assert size > (path / "manifest.json").stat().st_size
    GeneratedCatalog(tmp_path, max_records=41, max_bytes=size).verify("workspace-a", revision)
    with pytest.raises(CatalogError, match="CATALOG_LIMIT_EXCEEDED"):
        GeneratedCatalog(tmp_path, max_bytes=size - 1).verify("workspace-a", revision)


@pytest.mark.parametrize("size", [0, 17, 65536, 65537, 150000])
def test_bounded_read_preserves_bytes_at_exact_limit(tmp_path, size):
    value = bytes(i % 251 for i in range(size))
    path = tmp_path / "bounded.bin"
    path.write_bytes(value)
    assert bounded_read(path, size) == value


def test_bounded_read_caps_buffers_and_detects_growth_after_stat():
    class BoundedStream(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 65536
            return super().read(size)

    class GrowingFile:
        def stat(self):
            return SimpleNamespace(st_size=1)

        def open(self, mode):
            assert mode == "rb"
            return BoundedStream(b"x" * 150001)

    with pytest.raises(CatalogError, match="CATALOG_LIMIT_EXCEEDED") as exc:
        bounded_read(GrowingFile(), 150000)
    assert exc.value.status == 413


def test_bounded_read_small_file_does_not_allocate_catalog_limit():
    class SmallStream(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 65536
            return super().read(size)

    class SmallFile:
        def stat(self):
            return SimpleNamespace(st_size=3)

        def open(self, mode):
            return SmallStream(b"abc")

    assert bounded_read(SmallFile(), 100 * 1024 * 1024) == b"abc"


def test_duplicate_kind_cannot_hide_records_behind_manifest_counts(tmp_path):
    def mutate(manifest, content):
        datasets = [json.loads(line) for line in content["datasets.jsonl"].splitlines()]
        original = next(row for row in datasets if row["kind"] == "cpt")
        extra = copy.deepcopy(original)
        extra["id"] += "-extra"
        extra["version_id"] += "-extra"
        datasets.append(extra)
        content["datasets.jsonl"] = b"".join(json_bytes(row) for row in datasets)
        samples = [json.loads(line) for line in content["datasets/cpt.jsonl"].splitlines()]
        additional = copy.deepcopy(samples)
        for row in additional:
            row["id"] += "-extra"
            row["dataset_id"] = extra["id"]
        content["datasets/cpt.jsonl"] = b"".join(json_bytes(row) for row in samples + additional)
        files = [json.loads(line) for line in content["files.jsonl"].splitlines()]
        for row in files:
            if any(ref["id"] == original["version_id"] for ref in row["dataset_refs"]):
                row["dataset_refs"].append(
                    {
                        "catalog": "generated",
                        "type": "dataset_version",
                        "id": extra["version_id"],
                    }
                )
        content["files.jsonl"] = b"".join(json_bytes(row) for row in files)
        # All references and file hashes are self-consistent, but counts still describe 41
        # records while there are now 64. A kind-keyed dict used to overwrite this extra CPT.

    revision, _ = candidate(tmp_path, mutate=mutate)
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        GeneratedCatalog(tmp_path).publish("workspace-a", revision)


def test_empty_catalog_still_requires_each_kind(tmp_path):
    def mutate(manifest, content):
        rows = [json.loads(line) for line in content["datasets.jsonl"].splitlines()]
        content["datasets.jsonl"] = b"".join(
            json_bytes(row) for row in rows if row["kind"] != "dpo"
        )
        del manifest["counts"]["datasets"]["dpo"]

    revision, _ = candidate(tmp_path, counts=(0, 0, 0), mutate=mutate)
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        GeneratedCatalog(tmp_path).publish("workspace-a", revision)


@pytest.mark.parametrize("name", ["manifest.json", "sources.jsonl", "datasets/cpt.jsonl"])
def test_missing_file_is_not_an_empty_catalog(published, name):
    store, _, path = published
    (path / name).unlink()
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.load("workspace-a")


def test_invalid_registry_is_not_an_empty_catalog(published):
    store, _, _ = published
    registry = store.root / "workspace-a/catalog.json"
    registry.write_text(
        '{"schema_version":"catalog-index.v1","schema_version":"bad"}', encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.load("workspace-a")


def test_unimplemented_processing_schema_is_explicit(tmp_path):
    def mutate(manifest, content):
        content["processing-runs.jsonl"] = json_bytes({"status": "succeeded"})

    revision, _ = candidate(tmp_path, mutate=mutate)
    with pytest.raises(CatalogError, match="ADAPTER_UNAVAILABLE"):
        GeneratedCatalog(tmp_path).verify("workspace-a", revision)


def test_cache_is_bounded_and_workspaces_are_separate(tmp_path):
    store = GeneratedCatalog(tmp_path, cache_size=1)
    for workspace in ("workspace-a", "workspace-b"):
        revision, _ = candidate(tmp_path, workspace=workspace)
        store.publish(workspace, revision)
        assert store.load(workspace).scope.workspace_id == workspace
    assert len(store._cache) == 1
    assert store.load("workspace-a").scope.workspace_id == "workspace-a"
    assert len(store._cache) == 1


def test_query_result_isolated_without_copying_full_catalog(published, monkeypatch):
    from corpusflow.modules.training_center import catalog
    from corpusflow.modules.training_center.query import CatalogQueries

    store, revision, path = published
    original = catalog.copy_snapshot
    copied = []

    def recording_copy(value):
        copied.append(value)
        return original(value)

    monkeypatch.setattr(catalog, "copy_snapshot", recording_copy)
    result = store.execute("workspace-a", revision, lambda s: CatalogQueries(s).overview())
    assert len(copied) == 1 and copied[0] is not store._cache[next(iter(store._cache))]
    result.datasets[0].name = "poisoned"
    fresh = store.execute("workspace-a", revision, lambda s: CatalogQueries(s).overview())
    assert fresh.datasets[0].name != "poisoned"
    file = path / "datasets/cpt.jsonl"
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        store.execute("workspace-a", revision, lambda s: CatalogQueries(s).overview())
