"""Build contract-shaped processing views from persisted execution evidence."""

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
from corpusflow.db.models import Asset, NodeRun, PipelineRun

RunStatus = Literal["queued", "running", "succeeded", "partial", "failed"]
Unit = Literal["file", "record", "segment"]


def _utc(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _ref(object_type: str, object_id: str) -> ObjectRef:
    return ObjectRef(catalog="workspace", type=cast(Any, object_type), id=object_id)


def _run_status(status: str) -> RunStatus:
    if status in {"queued", "running", "succeeded", "partial", "failed"}:
        return cast(RunStatus, status)
    if status == "awaiting_review":
        return "partial"
    return "failed" if status in {"rejected", "isolated"} else "queued"


def _refs(value: list[dict[str, Any]] | None) -> list[ObjectRef]:
    if not value:
        return []
    result: list[ObjectRef] = []
    for item in value:
        if isinstance(item, dict) and item.get("catalog") and item.get("type") and item.get("id"):
            result.append(ObjectRef.model_validate(item))
    return result


def _unit(value: str | None, fallback: Unit) -> Unit:
    return cast(Unit, value if value in {"file", "record", "segment"} else fallback)


def build_processing_summary(
    session: Session,
    run: PipelineRun,
    *,
    scope: Scope | None = None,
    nodes: list[NodeRun] | None = None,
) -> ProcessingSummaryResponse:
    """Map only values persisted by the Worker into the frozen response contract."""
    asset = session.get(Asset, run.asset_id)
    file_ref = _ref("file", asset.id if asset else run.asset_id)
    if nodes is None:
        nodes = list(
            session.scalars(
                select(NodeRun)
                .where(NodeRun.run_id == run.id)
                .order_by(NodeRun.created_at, NodeRun.id)
            ).all()
        )
    # Historical attempts have no sequence. Preserve their recorded chronology,
    # then use the actual Worker start order for newly recorded attempts.
    nodes.sort(
        key=lambda node: (
            node.execution_sequence is not None,
            node.execution_sequence or 0,
            _utc(node.started_at or node.created_at),
            _utc(node.created_at),
            node.id,
        )
    )
    steps: list[ProcessingStepSummary] = []
    for sequence, node in enumerate(nodes, start=1):
        status = _run_status(node.status)
        input_unit = _unit(
            getattr(node, "input_unit", None), "file" if node.node_id == "parse" else "segment"
        )
        output_unit = _unit(getattr(node, "output_unit", None), "segment")
        raw_input_refs = getattr(node, "input_refs", None)
        input_refs = _refs(raw_input_refs)
        output_refs = _refs(getattr(node, "output_refs", None))
        steps.append(
            ProcessingStepSummary(
                id=node.id,
                run_id=run.id,
                attempt=max(1, node.attempt_no),
                operator_key=node.operator_key or node.node_id,
                operator_version=node.operator_version or "unknown",
                config_hash=_config_hash(node.config_snapshot or {}),
                sequence=sequence,
                status=status,
                input_count=node.input_count if node.status not in {"pending", "running"} else None,
                output_count=(
                    node.output_count if node.status not in {"pending", "running"} else None
                ),
                input_unit=input_unit,
                output_unit=output_unit,
                modified_count=getattr(node, "modified_count", None)
                if node.status not in {"pending", "running"}
                else None,
                filtered_count=getattr(node, "filtered_count", None)
                if node.status not in {"pending", "running"}
                else None,
                failed_count=getattr(node, "failed_count", None)
                if node.status not in {"pending", "running"}
                else None,
                input_refs=input_refs,
                output_refs=output_refs,
                started_at=_utc(getattr(node, "started_at", None))
                if getattr(node, "started_at", None)
                else None,
                completed_at=_utc(getattr(node, "completed_at", None))
                if getattr(node, "completed_at", None)
                else None,
            )
        )

    parse_steps = [step for step in steps if step.input_unit == "file"]
    parse = parse_steps[-1] if parse_steps else None
    final_outputs = steps[-1].output_refs if steps and steps[-1].output_refs else []
    final_output_count = (
        len(final_outputs)
        if final_outputs
        else (
            steps[-1].output_count
            if steps and steps[-1].status in {"succeeded", "partial"}
            else None
        )
    )
    file_output_count = 1 if parse and parse.status in {"succeeded", "partial"} else None
    totals = [
        ProcessingTotal(
            unit="file", input_count=1 if asset else None, output_count=file_output_count
        ),
        ProcessingTotal(
            unit="segment",
            input_count=parse.output_count if parse else None,
            output_count=final_output_count,
        ),
    ]
    as_of = (
        getattr(run, "finished_at", None)
        or getattr(run, "updated_at", None)
        or getattr(run, "created_at", None)
    )
    scope = scope or Scope(
        workspace_id=run.workspace_id,
        catalog="workspace",
        revision=str(run.revision),
        as_of=_utc(as_of),
        metric_definition_version="1.0.0",
    )
    return ProcessingSummaryResponse(
        scope=scope,
        run_id=run.id,
        status=_run_status(run.status),
        input_refs=[file_ref],
        output_refs=final_outputs,
        steps=steps,
        totals=totals,
    )
