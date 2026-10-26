"""Verified generated-v1 catalogs and explicit, atomic publication.

Run ``python -m corpusflow.modules.training_center.catalog --help`` to publish.
This module never accesses the database; callers must authorize the workspace.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

from pydantic import ValidationError

from corpusflow.contracts.training_center import models as m
from corpusflow.modules.training_center.generation import (
    KINDS,
    SCHEMA_VERSION,
    SPLITS,
    Json,
    json_bytes,
    sha256,
    validate_config,
)

SAMPLE_MODELS: dict[str, type[m.CptSample] | type[m.SftSample] | type[m.DpoSample]] = {
    "cpt": m.CptSample,
    "sft": m.SftSample,
    "dpo": m.DpoSample,
}
REQUIRED = {
    "sources.jsonl",
    "files.jsonl",
    "datasets.jsonl",
    "segments.jsonl",
    "processing-runs.jsonl",
    "lineage-edges.jsonl",
    *(f"datasets/{kind}.jsonl" for kind in KINDS),
}


class CatalogError(ValueError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def invalid() -> CatalogError:
    return CatalogError("CHECKSUM_MISMATCH", 409)


def revision_name(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise CatalogError("INVALID_ARGUMENT", 422)
    return value


def safe_child(root: Path, relative: str) -> Path:
    """Reject all symlinks/junctions, including links to another workspace in root."""
    parts = PurePosixPath(relative).parts
    if (
        not parts
        or relative != "/".join(parts)
        or "\\" in relative
        or ":" in relative
        or PurePosixPath(relative).is_absolute()
        or any(p in {".", ".."} for p in parts)
    ):
        raise invalid()
    path = root
    for part in parts:
        path /= part
        if path.is_symlink() or path.is_junction():
            raise invalid()
    if not path.resolve().is_relative_to(root.resolve()):
        raise invalid()
    return path


def bounded_read(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    return value


def decode_json(value: bytes) -> Any:
    # Duplicate keys and non-finite values must not acquire ambiguous hash semantics.
    def pairs(items: list[tuple[str, Any]]) -> Json:
        result: Json = {}
        for key, item in items:
            if key in result:
                raise invalid()
            result[key] = item
        return result

    def bad_constant(value: str) -> None:
        raise invalid()

    return json.loads(value.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)


@dataclass(frozen=True)
class CatalogSegment:
    id: str
    file_id: str
    language: str | None
    char_count: int


@dataclass(frozen=True)
class CatalogSnapshot:
    scope: m.Scope
    manifest: Json
    content_hash: str
    sources: dict[str, Json]
    files: tuple[m.FileSummary, ...]
    datasets: tuple[m.DatasetSummary, ...]
    samples: tuple[m.Sample, ...]
    segments: tuple[CatalogSegment, ...] = ()
    sample_files: dict[tuple[str, str, str], set[str]] = field(default_factory=dict)
    version_metadata: dict[str, Json] = field(default_factory=dict)
    file_runs: dict[str, str] = field(default_factory=dict)


class GeneratedCatalog:
    """Bounded cache of decoded snapshots, rechecking file bytes on every load.

    The publisher is a single administrative writer. API workers only read the
    registry; atomic replace gives them either complete registry version.
    """

    def __init__(
        self,
        root: Path,
        max_records: int = 100_000,
        max_bytes: int = 100 * 1024 * 1024,
        cache_size: int = 2,
    ) -> None:
        if not 1 <= max_records <= 100_000 or not 1 <= max_bytes <= 100 * 1024 * 1024:
            raise ValueError("catalog limits may only be lowered")
        if not 1 <= cache_size <= 10:
            raise ValueError("cache_size must be between 1 and 10")
        self.root = root.resolve()
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple[str, str, str], CatalogSnapshot] = OrderedDict()
        self._lock = RLock()

    def _workspace(self, workspace: str) -> Path:
        try:
            validate_config(workspace, 0, {})
        except ValueError:
            raise CatalogError("INVALID_ARGUMENT", 422) from None
        return safe_child(self.root, workspace)

    def _registry(self, workspace: str) -> Json:
        path = safe_child(self._workspace(workspace), "catalog.json")
        if not path.exists():
            raise CatalogError("NOT_FOUND", 404)
        registry = decode_json(bounded_read(path, min(self.max_bytes, 1024 * 1024)))
        if (
            not isinstance(registry, dict)
            or registry.get("schema_version") != "catalog-index.v1"
            or registry.get("workspace_id") != workspace
        ):
            raise invalid()
        for key in ("revisions", "retired_revisions"):
            values = registry.get(key)
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise invalid()
            if len(values) != len(set(values)):
                raise invalid()
            for value in values:
                revision_name(value)
        active = registry.get("active_revision")
        previous = registry.get("previous_revision")
        if active not in registry["revisions"] or (
            previous is not None and previous not in registry["revisions"]
        ):
            raise invalid()
        if set(registry["revisions"]) & set(registry["retired_revisions"]):
            raise invalid()
        hashes = registry.get("manifest_hashes")
        if not isinstance(hashes, dict) or set(hashes) != set(
            registry["revisions"] + registry["retired_revisions"]
        ):
            raise invalid()
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in hashes.values()
        ):
            raise invalid()
        return registry

    def load(self, workspace: str, revision: str | None = None) -> CatalogSnapshot:
        """Load only explicitly published versions, never arbitrary generated folders."""
        try:
            if revision is not None:
                revision_name(revision)
            registry = self._registry(workspace)
            selected = revision or registry["active_revision"]
            if selected not in registry["revisions"]:
                raise CatalogError("SNAPSHOT_EXPIRED", 409)
            snapshot = self.verify(workspace, selected)
            if snapshot.content_hash != registry["manifest_hashes"][selected]:
                raise invalid()
            return snapshot
        except CatalogError:
            raise
        except (OSError, ValueError, TypeError, KeyError):
            raise invalid() from None

    def verify(self, workspace: str, revision: str) -> CatalogSnapshot:
        """Validate a candidate before publication; does not make it visible."""
        try:
            directory = safe_child(self._workspace(workspace), revision_name(revision))
            manifest_path = safe_child(directory, "manifest.json")
            manifest = decode_json(bounded_read(manifest_path, self.max_bytes))
            if not isinstance(manifest, dict):
                raise invalid()
            if (
                manifest.get("schema_version") != SCHEMA_VERSION
                or manifest.get("workspace_id") != workspace
                or manifest.get("revision") != revision
            ):
                raise invalid()
            core = {k: v for k, v in manifest.items() if k not in {"revision", "generated_at"}}
            if sha256(json_bytes(core)) != revision:
                raise invalid()
            entries = manifest["content_files"]
            if not isinstance(entries, list):
                raise invalid()
            seen: set[str] = set()
            raw: dict[str, bytes] = {}
            total = 0
            sample_count = 0
            sizes: dict[str, int] = {}
            for entry in entries:
                name = entry["path"]
                if not isinstance(name, str) or name in seen or name == "manifest.json":
                    raise invalid()
                seen.add(name)
                value = bounded_read(safe_child(directory, name), self.max_bytes - total)
                total += len(value)
                lines = value.splitlines()
                if (
                    sha256(value) != entry["sha256"]
                    or len(lines) != entry["line_count"]
                    or len(value) != entry["size_bytes"]
                ):
                    raise invalid()
                sizes[name] = len(value)
                if name in {f"datasets/{kind}.jsonl" for kind in KINDS}:
                    sample_count += len(lines)
                    if sample_count > self.max_records:
                        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
                if name.endswith(".jsonl"):
                    raw[name] = value
            if not REQUIRED.issubset(seen):
                raise invalid()
            # v1 has no agreed persisted processed-record schema yet. Fail explicitly.
            if any(
                raw[name]
                for name in ("segments.jsonl", "processing-runs.jsonl", "lineage-edges.jsonl")
            ):
                raise CatalogError("ADAPTER_UNAVAILABLE", 503)
            content_hash = sha256(json_bytes(manifest))
            key = (workspace, revision, content_hash)
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return copy.deepcopy(cached)
            rows = {
                name: [decode_json(line) for line in value.splitlines()]
                for name, value in raw.items()
            }
            snapshot = self._decode(workspace, manifest, content_hash, rows, sizes)
            with self._lock:
                self._cache[key] = snapshot
                self._cache.move_to_end(key)
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            return copy.deepcopy(snapshot)
        except CatalogError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            raise invalid() from None

    def _decode(
        self,
        workspace: str,
        manifest: Json,
        content_hash: str,
        rows: dict[str, list[Json]],
        sizes: dict[str, int],
    ) -> CatalogSnapshot:
        scope = m.Scope(
            workspace_id=workspace,
            catalog="generated",
            revision=manifest["revision"],
            as_of=manifest["generated_at"],
            metric_definition_version="1.0.0",
        )
        sources: dict[str, Json] = {}
        for source in rows["sources.jsonl"]:
            m.SourceSummary.model_validate(
                {
                    "name": source["title"],
                    **{key: source[key] for key in ("id", "kind", "author", "url", "license")},
                }
            )
            if source["workspace_id"] != workspace or source["id"] in sources:
                raise invalid()
            sources[source["id"]] = source
        files = tuple(
            m.FileSummary.model_validate({k: v for k, v in row.items() if k != "relative_path"})
            for row in rows["files.jsonl"]
        )
        datasets = tuple(m.DatasetSummary.model_validate(row) for row in rows["datasets.jsonl"])
        samples = tuple(
            SAMPLE_MODELS[kind].model_validate(row)
            for kind in KINDS
            for row in rows[f"datasets/{kind}.jsonl"]
        )
        for collection in (files, datasets, samples):
            if len({r.id for r in collection}) != len(collection):
                raise invalid()
            if any(r.workspace_id != workspace for r in collection):
                raise invalid()
        versions = {d.version_id: d for d in datasets}
        dataset_map = {(d.id, d.version): d for d in datasets}
        if len(versions) != len(datasets):
            raise invalid()

        def source_ref(reference: m.ObjectRef) -> Json:
            if (
                reference.catalog != "generated"
                or reference.type != "source"
                or reference.id not in sources
            ):
                raise invalid()
            return sources[reference.id]

        group_splits: dict[str, str] = {}
        sequences: set[tuple[str, str, int]] = set()
        for sample in samples:
            dataset = dataset_map.get((sample.dataset_id, sample.dataset_version))
            if dataset is None or dataset.kind != sample.kind or sample.segment_refs:
                raise invalid()
            if not sample.source_refs:
                raise invalid()
            for reference in sample.source_refs:
                source = source_ref(reference)
                if (
                    source["source_group_id"] != sample.source_group_id
                    or source["split"] != sample.split
                ):
                    raise invalid()
            if group_splits.setdefault(sample.source_group_id, sample.split) != sample.split:
                raise invalid()
            sequence_key = (sample.dataset_id, sample.dataset_version, sample.sequence)
            if sequence_key in sequences:
                raise invalid()
            sequences.add(sequence_key)
            if sample.kind == "cpt":
                char_count = len(sample.text)
            elif sample.kind == "sft":
                char_count = sum(len(message.content) for message in sample.messages)
            else:
                char_count = len(sample.prompt) + len(sample.chosen) + len(sample.rejected)
            if sample.char_count != char_count:
                raise invalid()
        for dataset in datasets:
            selected = [
                s
                for s in samples
                if (s.dataset_id, s.dataset_version) == (dataset.id, dataset.version)
            ]
            counts: Counter[str] = Counter(s.split for s in selected)
            if dataset.record_count != len(selected) or dataset.split_counts.model_dump() != {
                s: counts[s] for s in SPLITS
            }:
                raise invalid()
            for reference in dataset.source_refs:
                source_ref(reference)
            if {r.id for r in dataset.source_refs} != {
                r.id for s in selected for r in s.source_refs
            }:
                raise invalid()
        for file, raw in zip(files, rows["files.jsonl"], strict=True):
            source = source_ref(file.source_ref)
            if (
                file.source_kind != source["kind"]
                or file.size_bytes != sizes.get(raw["relative_path"])
                or file.segment_count != 0
                or file.processing_status != "unprocessed"
            ):
                raise invalid()
            for reference in file.dataset_refs:
                if (
                    reference.catalog != "generated"
                    or reference.type != "dataset_version"
                    or reference.id not in versions
                ):
                    raise invalid()
                if file.source_ref.id not in {r.id for r in versions[reference.id].source_refs}:
                    raise invalid()
            expected_versions = {
                d.version_id
                for d in datasets
                if file.source_ref.id in {r.id for r in d.source_refs}
            }
            if (
                len(file.dataset_refs) != len(expected_versions)
                or {r.id for r in file.dataset_refs} != expected_versions
            ):
                raise invalid()
        expected_counts = {
            "files": len(files),
            "sources": len(sources),
            "segments": 0,
            "datasets": {
                d.kind: {
                    "record_count": d.record_count,
                    "record_unit": d.record_unit,
                    "split_counts": d.split_counts.model_dump(),
                }
                for d in datasets
            },
            "source_kinds": dict(Counter(s["kind"] for s in sources.values())),
        }
        if manifest.get("counts") != expected_counts:
            raise invalid()
        return CatalogSnapshot(scope, manifest, content_hash, sources, files, datasets, samples)

    def _write_registry(self, workspace: str, registry: Json) -> None:
        directory = self._workspace(workspace)
        destination = safe_child(directory, "catalog.json")
        descriptor, name = tempfile.mkstemp(prefix=".catalog-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(json_bytes(registry))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, destination)
        finally:
            Path(name).unlink(missing_ok=True)

    def publish(self, workspace: str, revision: str) -> None:
        """Admin/local operation only; never exposed as an HTTP endpoint."""
        with self._lock:
            snapshot = self.verify(workspace, revision)
            try:
                registry = self._registry(workspace)
            except CatalogError as exc:
                if exc.code != "NOT_FOUND":
                    raise
                registry = {
                    "schema_version": "catalog-index.v1",
                    "workspace_id": workspace,
                    "active_revision": None,
                    "previous_revision": None,
                    "revisions": [],
                    "retired_revisions": [],
                    "manifest_hashes": {},
                }
            if revision in registry["retired_revisions"]:
                raise CatalogError("SNAPSHOT_EXPIRED", 409)
            if (
                revision in registry["manifest_hashes"]
                and registry["manifest_hashes"][revision] != snapshot.content_hash
            ):
                raise invalid()
            if revision == registry["active_revision"]:
                return
            registry["previous_revision"] = registry["active_revision"]
            registry["active_revision"] = revision
            if revision not in registry["revisions"]:
                registry["revisions"].append(revision)
            registry["manifest_hashes"][revision] = snapshot.content_hash
            self._write_registry(workspace, registry)

    def retire(self, workspace: str, revision: str) -> None:
        with self._lock:
            revision_name(revision)
            registry = self._registry(workspace)
            if revision in {registry["active_revision"], registry["previous_revision"]}:
                raise CatalogError("INVALID_STATE_TRANSITION", 409)
            if revision not in registry["revisions"]:
                raise CatalogError("SNAPSHOT_EXPIRED", 409)
            registry["revisions"].remove(revision)
            registry["retired_revisions"].append(revision)
            self._write_registry(workspace, registry)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publish", "retire"))
    parser.add_argument("--data-dir", type=Path, default=Path(".local/training-center"))
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        catalog = GeneratedCatalog(args.data_dir)
        getattr(catalog, args.action)(args.workspace_id, args.revision)
    except (CatalogError, OSError, ValidationError) as exc:
        parser.exit(2, f"catalog operation failed: {type(exc).__name__}: {exc}\n")
    print(f"{args.action}: {args.workspace_id}/{args.revision}")


if __name__ == "__main__":
    main()
