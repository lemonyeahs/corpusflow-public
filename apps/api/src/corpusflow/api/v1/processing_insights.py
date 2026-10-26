"""Contract-shaped processing summaries and batch export endpoints."""

# FastAPI dependency declarations intentionally call Depends in signatures.
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.api.dependencies import actor_id, db, workspace_id
from corpusflow.db.models import DocumentVersion, PipelineRun, Segment
from corpusflow.services.processing_exports import serialize_records
from corpusflow.services.processing_insights import build_processing_summary

router = APIRouter(prefix="/api/v1", tags=["processing-insights"])


def _authorized_run(run_id: str, request: Request, session: Session) -> PipelineRun:
    user = actor_id(request, session)
    workspace = workspace_id(request, session, user)
    run = session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == workspace)
    )
    if not run:
        raise HTTPException(404, "NOT_FOUND")
    return run


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
    export_format: str = Query(default="jsonl"),
    session: Session = Depends(db),
)-> StreamingResponse:
    run = _authorized_run(run_id, request, session)
    if run.status not in {"succeeded", "partial"}:
        raise HTTPException(409, "INVALID_STATE_TRANSITION")
    version = session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.run_id == run.id)
        .order_by(DocumentVersion.version_no.desc(), DocumentVersion.created_at.desc())
    )
    records = []
    if version:
        records = [
            {
                "id": segment.id,
                "text": segment.text,
                "source_id": segment.source_id,
                "location": segment.location_json,
                "split": "unassigned",
            }
            for segment in session.scalars(
                select(Segment)
                .where(Segment.document_version_id == version.id)
                .order_by(Segment.created_at, Segment.id)
            ).all()
        ]
    try:
        export = serialize_records(records, "cleaned", export_format)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(422, "VALIDATION_FAILED") from exc
    response = StreamingResponse(export.chunks, media_type=export.content_type)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="pipeline-{run.id}.{export.extension}"'
    )
    return response


@router.get("/pipeline-runs/{run_id}/steps/{step_id}/comparison")
def pipeline_step_comparison(
    run_id: str,
    step_id: str,
    request: Request,
    record_id: str | None = None,
    session: Session = Depends(db),
)-> None:
    _authorized_run(run_id, request, session)
    # A stable pre/post record ID mapping is not persisted by the current schema.
    # Returning the contract error prevents silently pairing rows by position.
    del step_id, record_id
    raise HTTPException(404, "COMPARISON_NOT_AVAILABLE")
