"""Workspace database snapshots. No generated fallback or database mutations."""

from __future__ import annotations

import time
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.contracts.training_center import models as m
from corpusflow.db.models import (
    Asset,
    AssetBlob,
    CandidateSample,
    Dataset,
    DatasetVersion,
    DatasetVersionSample,
    Document,
    DocumentVersion,
    PipelineRun,
    Segment,
    Source,
)
from corpusflow.modules.training_center.catalog import (
    SAMPLE_MODELS,
    CatalogError,
    CatalogSegment,
    CatalogSnapshot,
)
from corpusflow.modules.training_center.generation import Json, json_bytes
from corpusflow.modules.training_center.processing import capture_processing
from corpusflow.modules.training_center.snapshot_copy import copy_snapshot
from corpusflow.services.training_center_graph import capture_graph


def utc(value: datetime) -> str:
    return (
        value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        if value.tzinfo is None
        else value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    )


def reference(kind: m.ObjectType, identifier: str) -> m.ObjectRef:
    return m.ObjectRef(catalog="workspace", type=kind, id=identifier)


class WorkspaceCatalogProvider(Protocol):
    """Python injection boundary, not a new wire revision protocol.

    Catalog, processing and graph reads share this store. Callers must authorize
    membership on every request before load.
    """

    def load(
        self,
        workspace: str,
        revision: str | None,
        session: Session,
        max_records: int = 100_000,
        max_bytes: int = 100 * 1024 * 1024,
    ) -> CatalogSnapshot: ...


def snapshot_from_database(
    session: Session, workspace: str, max_records: int, max_bytes: int
) -> CatalogSnapshot:
    """Read one repeatable DB transaction; only published training versions are counted."""
    raw_bytes = 0

    def account(row: Any) -> None:
        nonlocal raw_bytes
        for column in row.__table__.columns:
            value = getattr(row, column.key if column.key != "metadata" else "metadata_json")
            if isinstance(value, str):
                raw_bytes += len(value.encode("utf-8"))
            elif isinstance(value, (dict, list)):
                raw_bytes += len(json_bytes(value))
        if raw_bytes > max_bytes:
            raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)

    def rows(model: Any) -> list[Any]:
        result = []
        for row in session.scalars(
            select(model)
            .where(model.workspace_id == workspace)
            .limit(max_records + 1)
            .execution_options(yield_per=1)
        ):
            account(row)
            result.append(row)
            if len(result) > max_records:
                raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
        return result

    source_rows = rows(Source)
    sources: dict[str, Json] = {}
    for source in source_rows:
        kind = source.kind if source.kind in {"web", "book", "paper"} else "other"
        sources[source.id] = {
            "id": source.id,
            "title": source.name,
            "kind": kind,
            "author": None,
            "url": None,
            "license": None,
        }
    assets = {a.id: a for a in rows(Asset)}
    blobs = {b.id: b for b in rows(AssetBlob)}
    documents = {d.id: d for d in rows(Document) if d.asset_id in assets}
    versions = {v.id: v for v in rows(DocumentVersion) if v.document_id in documents}
    latest: dict[str, str] = {}
    for version in sorted(versions.values(), key=lambda v: (v.version_no, v.created_at, v.id)):
        latest[version.document_id] = version.id
    segments = {
        s.id: s
        for s in rows(Segment)
        if s.document_version_id in versions and s.source_id in sources
    }
    segment_files = {
        sid: documents[versions[s.document_version_id].document_id].asset_id
        for sid, s in segments.items()
    }
    latest_ids = set(latest.values())
    current_segments = tuple(
        CatalogSegment(s.id, segment_files[s.id], assets[segment_files[s.id]].language, len(s.text))
        for s in segments.values()
        if s.document_version_id in latest_ids
    )
    dataset_rows = {d.id: d for d in rows(Dataset) if d.product_type in {"pretrain", "sft", "dpo"}}
    published = {
        v.id: v
        for v in rows(DatasetVersion)
        if v.status == "published" and v.dataset_id in dataset_rows
    }
    pipeline_rows = rows(PipelineRun)
    pipelines = {run.id: run for run in pipeline_rows}
    linked = session.execute(
        select(CandidateSample, DatasetVersionSample)
        .join(DatasetVersionSample, DatasetVersionSample.candidate_sample_id == CandidateSample.id)
        .join(DatasetVersion, DatasetVersion.id == DatasetVersionSample.dataset_version_id)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(
            CandidateSample.workspace_id == workspace,
            DatasetVersion.workspace_id == workspace,
            DatasetVersion.status == "published",
            Dataset.workspace_id == workspace,
            Dataset.product_type.in_(("pretrain", "sft", "dpo")),
        )
        .order_by(
            DatasetVersionSample.dataset_version_id,
            CandidateSample.created_at,
            CandidateSample.id,
        )
        .limit(max_records + 1)
        .execution_options(yield_per=1)
    )
    samples: list[m.Sample] = []
    sample_files: dict[tuple[str, str, str], set[str]] = {}
    sample_runs: dict[tuple[str, str, str], tuple[str, ...]] = {}
    version_samples: dict[str, list[m.Sample]] = {vid: [] for vid in published}
    sequences: Counter[str] = Counter()
    dataset_sources: dict[str, set[str]] = {vid: set() for vid in published}
    file_datasets: dict[str, set[str]] = {aid: set() for aid in assets}
    bytes_used = 0
    for candidate, link in linked:
        account(candidate)
        if len(samples) >= max_records:
            raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
        version = published[link.dataset_version_id]
        dataset = dataset_rows[version.dataset_id]
        kind = "cpt" if dataset.product_type == "pretrain" else dataset.product_type
        payload = candidate.payload
        if not isinstance(payload, dict):
            raise CatalogError("INVALID_SAMPLE_FORMAT", 409)
        evidence = payload.get("evidence_ids")
        if evidence is None:
            metadata_value = payload.get("metadata")
            evidence = (
                metadata_value.get("segment_ids", []) if isinstance(metadata_value, dict) else []
            )
        if (
            not isinstance(evidence, list)
            or not evidence
            or candidate.source_id not in sources
            or any(sid not in segments for sid in evidence)
        ):
            raise CatalogError("INVALID_SAMPLE_EVIDENCE", 409)
        refs = list(
            dict.fromkeys([candidate.source_id, *(segments[sid].source_id for sid in evidence)])
        )
        if kind == "cpt":
            values = {"text": payload["text"], "title": payload.get("title")}
            chars = len(payload["text"])
        elif kind == "sft":
            values = {"messages": payload["messages"]}
            chars = sum(len(message["content"]) for message in payload["messages"])
        else:
            values = {key: payload[key] for key in ("prompt", "chosen", "rejected")}
            if "preference_reason" in payload:
                values["preference_reason"] = payload["preference_reason"]
            chars = sum(len(payload[key]) for key in ("prompt", "chosen", "rejected"))
        sequences[version.id] += 1
        file_ids = {segment_files[sid] for sid in evidence}
        languages = {assets[aid].language for aid in file_ids}
        sample = SAMPLE_MODELS[kind].model_validate(
            {
                "id": candidate.id,
                "workspace_id": workspace,
                "kind": kind,
                "dataset_id": dataset.id,
                "dataset_version": version.version,
                "sequence": sequences[version.id],
                "split": link.split,
                "source_group_id": candidate.source_id,
                "source_refs": [reference("source", sid).model_dump() for sid in refs],
                "segment_refs": [reference("segment", sid).model_dump() for sid in evidence],
                "language": next(iter(languages)) if len(languages) == 1 else None,
                "char_count": chars,
                "token_count": None,
                "token_count_method": None,
                **values,
            }
        )
        bytes_used += len(json_bytes(sample.model_dump()))
        if bytes_used > max_bytes:
            raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
        samples.append(sample)
        version_samples[version.id].append(sample)
        sample_files[(sample.dataset_id, sample.dataset_version, sample.id)] = file_ids
        sample_runs[(sample.dataset_id, sample.dataset_version, sample.id)] = tuple(
            sorted(
                {
                    run_id
                    for sid in evidence
                    if (run_id := versions[segments[sid].document_version_id].run_id) is not None
                    and run_id in pipelines
                    and pipelines[run_id].asset_id == segment_files[sid]
                }
            )
        )
        dataset_sources[version.id].update(refs)
        for aid in file_ids:
            file_datasets[aid].add(version.id)
    datasets: list[m.DatasetSummary] = []
    metadata: dict[str, Json] = {}
    for version in published.values():
        dataset = dataset_rows[version.dataset_id]
        selected = version_samples[version.id]
        kind = "cpt" if dataset.product_type == "pretrain" else dataset.product_type
        datasets.append(
            m.DatasetSummary.model_validate(
                {
                    "id": dataset.id,
                    "workspace_id": workspace,
                    "version": version.version,
                    "version_id": version.id,
                    "kind": kind,
                    "product_type": dataset.product_type,
                    "name": dataset.name,
                    "record_count": len(selected),
                    "record_unit": {"cpt": "article", "sft": "record", "dpo": "pair"}[kind],
                    "split_counts": {
                        split: sum(s.split == split for s in selected)
                        for split in ("train", "validation", "test")
                    },
                    "token_count": None,
                    "token_count_method": None,
                    "status": version.status,
                    "source_refs": [
                        reference("source", sid).model_dump()
                        for sid in sorted(dataset_sources[version.id])
                    ],
                }
            )
        )
        metadata[version.id] = {
            "manifest_storage_key": version.manifest_storage_key,
            "manifest_sha256": version.manifest_sha256,
        }
    runs: dict[str, Any] = {}
    for run in sorted(pipeline_rows, key=lambda r: (r.created_at, r.id)):
        if run.asset_id in assets:
            runs[run.asset_id] = run
    counts = Counter(s.file_id for s in current_segments)
    files: list[m.FileSummary] = []
    for asset in assets.values():
        if asset.blob_id not in blobs or asset.source_id not in sources:
            raise CatalogError("CHECKSUM_MISMATCH", 409)
        blob = blobs[asset.blob_id]
        status = runs[asset.id].status if asset.id in runs else "unprocessed"
        if status not in {"queued", "running", "succeeded", "partial", "failed"}:
            status = "unprocessed"
        files.append(
            m.FileSummary.model_validate(
                {
                    "id": asset.id,
                    "workspace_id": workspace,
                    "filename": asset.filename,
                    "format": asset.format
                    if asset.format in {"pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl"}
                    else "other",
                    "media_type": blob.media_type,
                    "size_bytes": blob.byte_size,
                    "source_ref": reference("source", asset.source_id).model_dump(),
                    "source_kind": sources[asset.source_id]["kind"],
                    "language": asset.language,
                    "ingested_at": utc(asset.created_at),
                    "processing_status": status,
                    "segment_count": counts[asset.id],
                    "dataset_refs": [
                        reference("dataset_version", vid).model_dump()
                        for vid in sorted(file_datasets[asset.id])
                    ],
                }
            )
        )
    bytes_used += sum(len(json_bytes(f.model_dump())) for f in files)
    bytes_used += sum(len(json_bytes(d.model_dump())) for d in datasets)
    bytes_used += sum(len(json_bytes(s)) for s in sources.values())
    bytes_used += sum(len(s.text.encode("utf-8")) for s in segments.values())
    if bytes_used > max_bytes:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    scope = m.Scope(
        workspace_id=workspace,
        catalog="workspace",
        revision=uuid4().hex,
        as_of=utc(datetime.now(UTC)),
        metric_definition_version="1.0.0",
    )
    return CatalogSnapshot(
        scope,
        {},
        "",
        sources,
        tuple(files),
        tuple(datasets),
        tuple(samples),
        current_segments,
        sample_files,
        metadata,
        {aid: r.id for aid, r in runs.items()},
        sample_runs,
    )


class WorkspaceSnapshots:
    def __init__(
        self, ttl: int = 900, capacity: int = 10, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if ttl <= 0 or capacity <= 0:
            raise ValueError("Snapshot TTL and capacity must be positive")
        self.ttl = min(ttl, 900)
        self.capacity = min(capacity, 10)
        self.clock = clock
        self._items: dict[str, OrderedDict[str, tuple[float, CatalogSnapshot]]] = {}
        self._lock = RLock()

    def load(
        self,
        workspace: str,
        revision: str | None,
        session: Session,
        max_records: int = 100_000,
        max_bytes: int = 100 * 1024 * 1024,
    ) -> CatalogSnapshot:
        with self._lock:
            for wid, bucket in list(self._items.items()):
                for key, (expires, _) in list(bucket.items()):
                    if expires <= self.clock():
                        del bucket[key]
                if not bucket:
                    del self._items[wid]
            items = self._items.setdefault(workspace, OrderedDict())
            if revision is not None:
                if revision not in items:
                    raise CatalogError("SNAPSHOT_EXPIRED", 409)
                return copy_snapshot(items[revision][1])
            try:
                with Session(bind=session.get_bind()) as reader:
                    if reader.get_bind().dialect.name == "postgresql":
                        reader.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                    elif reader.get_bind().dialect.name == "sqlite":
                        # SQLite's legacy driver mode does not BEGIN for a SELECT.
                        reader.connection().exec_driver_sql("BEGIN")
                    snapshot = snapshot_from_database(reader, workspace, max_records, max_bytes)
                    processing = capture_processing(reader, snapshot.scope, max_records, max_bytes)
                    graph = capture_graph(
                        reader, workspace, snapshot.scope, processing, max_records
                    )
                    snapshot = replace(snapshot, processing=processing, graph=graph)
                    if projection_bytes(snapshot) > max_bytes:
                        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
            except (ValidationError, KeyError, TypeError):
                raise CatalogError("INVALID_SAMPLE_FORMAT", 409) from None
            items[snapshot.scope.revision] = (self.clock() + self.ttl, snapshot)
            while len(items) > self.capacity:
                items.popitem(last=False)
            return copy_snapshot(snapshot)


def projection_bytes(value: Any) -> int:
    """Conservative UTF-8 budget for the entire projection, including duplicate views."""
    if isinstance(value, BaseModel):
        return len(value.model_dump_json().encode("utf-8")) + 2
    if is_dataclass(value) and not isinstance(value, type):
        return (
            sum(
                len(item.name) + projection_bytes(getattr(value, item.name)) + 4
                for item in fields(value)
            )
            + 2
        )
    if isinstance(value, dict):
        return (
            sum(
                len(str(key).encode("utf-8")) + projection_bytes(item) + 4
                for key, item in value.items()
            )
            + 2
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return sum(projection_bytes(item) + 1 for item in value) + 2
    return len(json_bytes(value)) + 2
