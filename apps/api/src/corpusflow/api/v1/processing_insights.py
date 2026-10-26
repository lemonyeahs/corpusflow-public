"""Authenticated, frozen processing reads and preflighted exports."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from corpusflow.api.v1.training_center import Read
from corpusflow.contracts.training_center import models as m
from corpusflow.core.errors import ErrorResponse
from corpusflow.modules.training_center.processing import FrozenProcessing, select_comparison
from corpusflow.services.processing_exports import ExportError, serialize_records

router = APIRouter(
    prefix="/api/v1",
    tags=["processing-insights"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 413, 422)},
)
ExportFormat = Literal["jsonl", "markdown", "csv", "txt"]


def frozen_run(read: Read, query: m.ProcessingQuery, run_id: str) -> FrozenProcessing:
    snapshot = read.query(query).snapshot
    run = snapshot.processing.get(run_id)
    if run is None:
        raise HTTPException(404, "NOT_FOUND")
    return run


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
            # checked against the frozen records before this function is called.
            handle.flush()
        return path, written, export.extension
    except Exception:
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


@router.get("/pipeline-runs/{run_id}/summary", response_model=m.ProcessingSummaryResponse)
def pipeline_run_summary(
    run_id: str, read: Read, query: Annotated[m.ProcessingQuery, Query()]
) -> m.ProcessingSummaryResponse:
    return frozen_run(read, query, run_id).summary


@router.get("/pipeline-runs/{run_id}/export")
def pipeline_run_export(
    run_id: str, read: Read, query: Annotated[m.ProcessingExportQuery, Query()]
) -> StreamingResponse:
    run = frozen_run(read, query, run_id)
    if (
        run.status != "succeeded"
        or not run.summary.steps
        or run.summary.steps[-1].status != "succeeded"
        or run.summary.steps[-1].output_count != len(run.records)
    ):
        raise HTTPException(409, "INVALID_STATE_TRANSITION")
    if len(run.records) > read.settings.training_center_max_records:
        raise HTTPException(413, "EXPORT_LIMIT_EXCEEDED")
    try:
        path, size, extension = _materialize_export(
            iter(run.records), query.export_format, read.settings.training_center_max_bytes
        )
    except ExportError as exc:
        if str(exc) == "EXPORT_LIMIT_EXCEEDED":
            raise HTTPException(413, "EXPORT_LIMIT_EXCEEDED") from exc
        raise HTTPException(422, "VALIDATION_FAILED") from exc
    filename = f"pipeline-{run_id}.{extension}"
    content_types = {
        "jsonl": "application/x-ndjson",
        "md": "text/markdown",
        "csv": "text/csv",
        "txt": "text/plain",
    }
    response = StreamingResponse(
        _stream_file(path, size),
        media_type=f"{content_types[extension]}; charset=utf-8",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )
    response.headers["Content-Disposition"] = (
        f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    )
    response.headers["Content-Length"] = str(size)
    response.headers["X-Training-Center-Revision"] = run.summary.scope.revision
    return response


@router.get(
    "/pipeline-runs/{run_id}/steps/{step_id}/comparison", response_model=m.ComparisonResponse
)
def pipeline_step_comparison(
    run_id: str, step_id: str, read: Read, query: Annotated[m.ProcessingComparisonQuery, Query()]
) -> m.ComparisonResponse:
    run = frozen_run(read, query, run_id)
    if not any(step.id == step_id for step in run.summary.steps):
        raise HTTPException(404, "NOT_FOUND")
    return select_comparison(run, query.record_id, step_id)
