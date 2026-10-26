from __future__ import annotations

import json
import os

import pytest
from corpusflow.modules.training_center.catalog import CatalogError, GeneratedCatalog, safe_child
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
