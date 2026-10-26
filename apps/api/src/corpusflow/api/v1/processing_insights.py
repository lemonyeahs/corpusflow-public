"""Authenticated processing summaries, comparisons and bounded exports.

The router is intentionally independent so the integration owner can register it
after the persistence and contract checks are reviewed.
"""

# FastAPI dependency declarations intentionally call Depends in signatures.
# ruff: noqa: B008

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from corpusflow.api.dependencies import actor_id, db, workspace_id
from corpusflow.contracts.training_center.models import (
    ComparisonResponse,
    ObjectRef,
    ProcessingRunRef,
    RecordContent,
)
from corpusflow.db.models import (
    DocumentVersion,
    NodeRun,
    PipelineRun,
    ProcessingRecordMap,
    Segment,
)
from corpusflow.services.processing_exports import ExportError, serialize_records
from corpusflow.services.processing_insights import build_processing_summary

router = APIRouter(prefix="/api/v1", tags=["processing-insights"])
ExportFormat = Literal["jsonl", "markdown", "csv", "txt"]


def _authorized_run(run_id: str, request: Request, session: Session) -> PipelineRun:
    user = actor_id(request, session)
    workspace = workspace_id(request, session, user)
    run = session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == workspace)
    )
    if not run:
        raise HTTPException(404, "NOT_FOUND")
    return run


def _limits(request: Request) -> tuple[int, int]:
    settings = getattr(request.app.state, "config", None)
    return (
        int(getattr(settings, "training_center_max_records", 100_000)),
        int(getattr(settings, "training_center_max_bytes", 104_857_600)),
    )


def _stream_file(path: Path, size: int) -> Iterator[bytes]:
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                yield chunk
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _materialize_export(
    records: Iterator[dict[str, object]],
    export_format: ExportFormat,
    max_bytes: int,
) -> tuple[Path, int, str]:
    """Serialize to a private temporary file before returning HTTP headers.

    This makes the record and byte budget check happen before a 200 response is
    sent, while keeping the response body itself streamed in bounded chunks.
    """
    path: Path | None = None
    written = 0
    try:
        with tempfile.NamedTemporaryFile(prefix="corpusflow-export-", delete=False) as handle:
            path = Path(handle.name)
            export = serialize_records(records, "cleaned", export_format)
            for chunk in export.chunks:
                if chunk:
                    written += len(chunk)
                    if written > max_bytes:
                        raise ExportError("EXPORT_LIMIT_EXCEEDED")
                    handle.write(chunk)
            # The serializer consumes the input iterator exactly once. Count is
            # checked by the route's SQL count before this function is called.
            handle.flush()
        return path, written, export.extension
    except Exception:
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


@router.get("/pipeline-runs/{run_id}/summary")
def pipeline_run_summary(
    run_id: str, request: Request, session: Session = Depends(db)
) -> dict[str, object]:
    run = _authorized_run(run_id, request, session)
    return build_processing_summary(session, run).model_dump(mode="json")


@router.get("/pipeline-runs/{run_id}/export")
def pipeline_run_export(
    run_id: str,
    request: Request,
    export_format: ExportFormat = Query(default="jsonl"),
    session: Session = Depends(db),
) -> StreamingResponse:
    run = _authorized_run(run_id, request, session)
    if run.status not in {"succeeded", "partial", "awaiting_review"}:
        raise HTTPException(409, "INVALID_STATE_TRANSITION")
    version = session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.run_id == run.id)
        .order_by(DocumentVersion.version_no.desc(), DocumentVersion.created_at.desc())
    )
    max_records, max_bytes = _limits(request)
    count = 0
    if version:
        count = int(
            session.scalar(
                select(func.count(Segment.id)).where(Segment.document_version_id == version.id)
            )
            or 0
        )
    if count > max_records:
        raise HTTPException(413, "EXPORT_LIMIT_EXCEEDED")

    def records() -> Iterator[dict[str, object]]:
        if not version:
            return
        for segment in session.scalars(
            select(Segment)
            .where(Segment.document_version_id == version.id)
            .order_by(Segment.created_at, Segment.id)
        ).yield_per(1000):
            yield {
                "id": segment.record_key or segment.id,
                "text": segment.text,
                "source_id": segment.source_id,
                "source_refs": [
                    {"catalog": "workspace", "type": "file", "id": run.asset_id}
                ],
                "location": segment.location_json,
                "split": "unassigned",
            }

    try:
        path, size, extension = _materialize_export(
            records(), export_format, max_bytes
        )
    except ExportError as exc:
        if str(exc) == "EXPORT_LIMIT_EXCEEDED":
            raise HTTPException(413, "EXPORT_LIMIT_EXCEEDED") from exc
        raise HTTPException(422, "VALIDATION_FAILED") from exc
    filename = f"pipeline-{run.id}.{extension}"
    content_types = {
        "jsonl": "application/x-ndjson",
        "md": "text/markdown",
        "csv": "text/csv",
        "txt": "text/plain",
    }
    response = StreamingResponse(
        _stream_file(path, size), media_type=f"{content_types[extension]}; charset=utf-8"
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'
    )
    response.headers["Content-Length"] = str(size)
    return response


@router.get("/pipeline-runs/{run_id}/steps/{step_id}/comparison")
def pipeline_step_comparison(
    run_id: str,
    step_id: str,
    request: Request,
    record_id: str | None = None,
    session: Session = Depends(db),
) -> dict[str, object]:
    run = _authorized_run(run_id, request, session)
    node = session.scalar(
        select(NodeRun).where(NodeRun.id == step_id, NodeRun.run_id == run.id)
    )
    if not node:
        raise HTTPException(404, "NOT_FOUND")
    maps = select(ProcessingRecordMap).where(
        ProcessingRecordMap.run_id == run.id,
        ProcessingRecordMap.node_run_id == node.id,
        ProcessingRecordMap.workspace_id == run.workspace_id,
    )
    if record_id:
        mapping = session.scalar(maps.where(ProcessingRecordMap.record_id == record_id))
    else:
        candidates = list(session.scalars(maps.limit(2)).all())
        mapping = candidates[0] if len(candidates) == 1 else None
    if not mapping or not mapping.before_segment_id or not mapping.after_segment_id:
        raise HTTPException(404, "COMPARISON_NOT_AVAILABLE")
    before = session.scalar(
        select(Segment).where(
            Segment.id == mapping.before_segment_id, Segment.workspace_id == run.workspace_id
        )
    )
    after = session.scalar(
        select(Segment).where(
            Segment.id == mapping.after_segment_id, Segment.workspace_id == run.workspace_id
        )
    )
    if not before or not after:
        raise HTTPException(404, "COMPARISON_NOT_AVAILABLE")
    summary = build_processing_summary(session, run)
    all_steps = list(
        session.scalars(
            select(NodeRun)
            .where(NodeRun.run_id == run.id)
            .order_by(NodeRun.created_at, NodeRun.id)
        ).all()
    )
    step_position = next(
        (index for index, value in enumerate(all_steps) if value.id == node.id), -1
    )
    applied_steps = [
        ObjectRef(catalog="workspace", type="operator_run", id=step.id)
        for step in all_steps[: step_position + 1]
    ]
    changes: list[str] = []
    if before.text != after.text:
        changes.append("text_changed")
    response = ComparisonResponse(
        scope=summary.scope,
        before=RecordContent(record_id=mapping.record_id, text=before.text),
        after=RecordContent(record_id=mapping.record_id, text=after.text),
        applied_steps=applied_steps,
        record_ref=ObjectRef(catalog="workspace", type="segment", id=after.id),
        processing_run_ref=ProcessingRunRef(catalog="workspace", type="pipeline_run", id=run.id),
        changes=changes,
    )
    return response.model_dump(mode="json")
