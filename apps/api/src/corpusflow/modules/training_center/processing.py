"""Immutable processing projections captured inside the workspace read transaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.contracts.training_center import models as m
from corpusflow.db.models import (
    Document,
    DocumentVersion,
    NodeRun,
    PipelineRun,
    ProcessingRecordMap,
    Segment,
)
from corpusflow.modules.training_center.catalog import CatalogError
from corpusflow.modules.training_center.generation import json_bytes
from corpusflow.services.processing_insights import build_processing_summary


@dataclass(frozen=True)
class FrozenProcessing:
    asset_id: str
    status: str
    summary: m.ProcessingSummaryResponse
    comparisons: tuple[m.ComparisonResponse, ...]
    records: tuple[dict[str, Any], ...]


def capture_processing(
    session: Session, scope: m.Scope, max_records: int, max_bytes: int
) -> dict[str, FrozenProcessing]:
    workspace = scope.workspace_id
    runs = list(
        session.scalars(
            select(PipelineRun)
            .where(PipelineRun.workspace_id == workspace)
            .order_by(PipelineRun.created_at, PipelineRun.id)
            .limit(max_records + 1)
        )
    )
    segments = list(
        session.scalars(
            select(Segment).where(Segment.workspace_id == workspace).limit(max_records + 1)
        )
    )
    mappings = list(
        session.scalars(
            select(ProcessingRecordMap)
            .where(ProcessingRecordMap.workspace_id == workspace)
            .order_by(ProcessingRecordMap.record_id, ProcessingRecordMap.id)
            .limit(max_records + 1)
        )
    )
    if max(len(runs), len(segments), len(mappings)) > max_records:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    by_id = {segment.id: segment for segment in segments}
    ownership = {
        version.id: (document.asset_id, version.run_id)
        for version, document in session.execute(
            select(DocumentVersion, Document)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.workspace_id == workspace, Document.workspace_id == workspace)
            .limit(max_records + 1)
        )
    }
    if len(ownership) > max_records:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    by_run: dict[str, list[ProcessingRecordMap]] = {}
    for mapping in mappings:
        by_run.setdefault(mapping.run_id, []).append(mapping)
    nodes = list(
        session.scalars(
            select(NodeRun)
            .join(PipelineRun, PipelineRun.id == NodeRun.run_id)
            .where(PipelineRun.workspace_id == workspace)
            .limit(max_records + 1)
        )
    )
    if len(nodes) > max_records:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    run_nodes: dict[str, list[NodeRun]] = {}
    for node in nodes:
        run_nodes.setdefault(node.run_id, []).append(node)
    result = {}
    used = 0
    for run in runs:
        summary = build_processing_summary(
            session, run, scope=scope, nodes=run_nodes.get(run.id, [])
        )
        steps = {step.id: step for step in summary.steps}
        comparisons = []
        for mapping in by_run.get(run.id, []):
            step = steps.get(mapping.node_run_id)
            before = by_id.get(mapping.before_segment_id or "")
            after = by_id.get(mapping.after_segment_id or "")
            if not step or not before or not after:
                continue
            # Both identities and hashes must still match the persisted execution evidence.
            if (
                before.record_key != mapping.record_id
                or after.record_key != mapping.record_id
                or before.content_hash != mapping.before_hash
                or after.content_hash != mapping.after_hash
                or ownership.get(before.document_version_id, (None, None))[0] != run.asset_id
                or ownership.get(after.document_version_id) != (run.asset_id, run.id)
                or not any(ref.type == "segment" and ref.id == before.id for ref in step.input_refs)
                or not any(ref.type == "segment" and ref.id == after.id for ref in step.output_refs)
            ):
                continue
            comparisons.append(
                m.ComparisonResponse(
                    scope=scope,
                    before=m.RecordContent(record_id=mapping.record_id, text=before.text),
                    after=m.RecordContent(record_id=mapping.record_id, text=after.text),
                    applied_steps=[
                        m.ObjectRef(catalog="workspace", type="operator_run", id=step.id)
                    ],
                    record_ref=m.ObjectRef(catalog="workspace", type="segment", id=after.id),
                    processing_run_ref=m.ProcessingRunRef(
                        catalog="workspace", type="pipeline_run", id=run.id
                    ),
                    changes=["text_changed"] if before.text != after.text else [],
                )
            )
        records: list[dict[str, Any]] = []
        if run.status == "succeeded":
            for ref in summary.output_refs:
                segment = by_id.get(ref.id) if ref.type == "segment" else None
                if segment is None or ownership.get(segment.document_version_id) != (
                    run.asset_id,
                    run.id,
                ):
                    raise CatalogError("CHECKSUM_MISMATCH", 409)
                records.append(
                    {
                        "id": segment.record_key or segment.id,
                        "text": segment.text,
                        "source_id": segment.source_id,
                        "source_refs": [
                            {"catalog": "workspace", "type": "file", "id": run.asset_id}
                        ],
                        "location": segment.location_json,
                        "split": "unassigned",
                    }
                )
        used += len(json_bytes(summary.model_dump()))
        used += sum(len(json_bytes(item.model_dump())) for item in comparisons)
        used += sum(len(json_bytes(item)) for item in records)
        if used > max_bytes:
            raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
        result[run.id] = FrozenProcessing(
            run.asset_id, run.status, summary, tuple(comparisons), tuple(records)
        )
    return result


def select_comparison(
    run: FrozenProcessing, record_id: str | None, step_id: str | None = None
) -> m.ComparisonResponse:
    """Default: changed records first, latest comparable step, stable record ID."""
    order = {step.id: step.sequence for step in run.summary.steps}
    candidates = [
        item
        for item in run.comparisons
        if (record_id is None or item.before.record_id == record_id)
        and (step_id is None or item.applied_steps[-1].id == step_id)
    ]
    if not candidates:
        raise CatalogError("COMPARISON_NOT_AVAILABLE", 404)
    return sorted(
        candidates,
        key=lambda item: (
            not bool(item.changes),
            -order[item.applied_steps[-1].id],
            item.before.record_id,
        ),
    )[0]
