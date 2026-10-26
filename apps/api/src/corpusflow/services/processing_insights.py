"""Build contract-shaped summaries from persisted pipeline execution records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.contracts.training_center.models import (
    ObjectRef,
    ProcessingStepSummary,
    ProcessingSummaryResponse,
    ProcessingTotal,
    Scope,
)
from corpusflow.db.models import Asset, DocumentVersion, NodeRun, PipelineRun, Segment

RunStatus = Literal["queued", "running", "succeeded", "partial", "failed"]
Unit = Literal["file", "record", "segment"]


def _utc(value: datetime | None) -> str:
    instant = (value or datetime.now(UTC)).astimezone(UTC)
    return instant.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _ref(object_type: str, object_id: str) -> ObjectRef:
    return ObjectRef(catalog="workspace", type=cast(Any, object_type), id=object_id)


def _run_status(status: str) -> RunStatus:
    if status in {"queued", "running", "succeeded", "partial", "failed"}:
        return cast(RunStatus, status)
    return "failed" if status in {"rejected", "isolated"} else "queued"


def _segments(session: Session, version_id: str) -> list[Segment]:
    return list(
        session.scalars(
            select(Segment)
            .where(Segment.document_version_id == version_id)
            .order_by(Segment.created_at, Segment.id)
        ).all()
    )


def build_processing_summary(session: Session, run: PipelineRun) -> ProcessingSummaryResponse:
    """Map database rows to the frozen ProcessingSummaryResponse contract."""
    asset = session.get(Asset, run.asset_id)
    file_ref = _ref("file", asset.id if asset else run.asset_id)
    versions = list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.run_id == run.id)
            .order_by(DocumentVersion.version_no, DocumentVersion.created_at)
        ).all()
    )
    latest_segments = _segments(session, versions[-1].id) if versions else []
    nodes = list(
        session.scalars(
            select(NodeRun).where(NodeRun.run_id == run.id).order_by(NodeRun.created_at, NodeRun.id)
        ).all()
    )
    steps: list[ProcessingStepSummary] = []
    previous_refs = [file_ref]
    for sequence, node in enumerate(nodes, start=1):
        status = _run_status(node.status)
        is_parse = node.node_id == "parse"
        input_unit: Unit = "file" if is_parse else "segment"
        output_unit: Unit = "segment"
        output_refs = [_ref("segment", segment.id) for segment in latest_segments]
        if is_parse:
            input_refs = [file_ref]
        else:
            input_refs = previous_refs
        failed_count = node.input_count if status == "failed" and input_unit == output_unit else 0
        step = ProcessingStepSummary(
            id=node.id,
            run_id=run.id,
            attempt=max(1, node.attempt_no),
            operator_key=node.operator_key or node.node_id,
            operator_version=node.operator_version or "unknown",
            config_hash=_config_hash(node.config_snapshot or {}),
            sequence=sequence,
            status=status,
            input_count=node.input_count if node.status not in {"pending", "running"} else None,
            output_count=node.output_count if node.status not in {"pending", "running"} else None,
            input_unit=input_unit,
            output_unit=output_unit,
            modified_count=None,
            filtered_count=(
                node.filtered_count if node.status not in {"pending", "running"} else None
            ),
            failed_count=failed_count if node.status not in {"pending", "running"} else None,
            input_refs=input_refs,
            output_refs=output_refs if status in {"succeeded", "partial"} else [],
            started_at=None,
            completed_at=(
                _utc(run.finished_at) if status in {"succeeded", "partial", "failed"} else None
            ),
        )
        steps.append(step)
        previous_refs = output_refs or previous_refs

    parse_count = next(
        (step.output_count for step in steps if step.input_unit == "file"),
        None,
    )
    segment_count = len(latest_segments)
    totals = [
        ProcessingTotal(unit="file", input_count=1, output_count=1 if asset else 0),
        ProcessingTotal(unit="segment", input_count=parse_count, output_count=segment_count),
    ]
    scope = Scope(
        workspace_id=run.workspace_id,
        catalog="workspace",
        revision=str(run.revision),
        as_of=_utc(run.finished_at),
        metric_definition_version="1.0.0",
    )
    return ProcessingSummaryResponse(
        scope=scope,
        run_id=run.id,
        status=_run_status(run.status),
        input_refs=[file_ref],
        output_refs=[_ref("segment", segment.id) for segment in latest_segments],
        steps=steps,
        totals=totals,
    )
