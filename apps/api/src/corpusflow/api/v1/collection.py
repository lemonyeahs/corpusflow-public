"""Discovery metadata and independently reviewed asynchronous acquisition."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.adapters.acquisition import SafeFetcher
from corpusflow.api.v1.business import audit, db, role_required
from corpusflow.api.v1.rag import context
from corpusflow.db.models import DiscoveryCandidate, IngestPlan
from corpusflow.services import acquisition, rag

router = APIRouter(prefix="/api/v1/collection", tags=["collection"])


class DOIIn(BaseModel):
    doi: str = Field(min_length=8, max_length=200)


class PlanIn(BaseModel):
    source_id: str
    candidate_ids: list[str] = Field(min_length=1, max_length=10)
    request_key: str = Field(min_length=1, max_length=120)


class ReviewIn(BaseModel):
    approve: bool
    legal_basis: str = Field(min_length=12, max_length=2000)


@router.post("/doi-metadata")
def doi(body: DOIIn, request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    actor, wid = context(request, session)
    role_required(session, actor, wid, {"engineer"})
    result = SafeFetcher(request.app.state.config.acquisition_hosts, max_bytes=1_000_000).doi(
        body.doi
    )
    audit(session, request, wid, actor, "collection.doi.read", "doi", body.doi)
    session.commit()
    return result


@router.get("/candidates")
def candidates(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    _, wid = context(request, session)
    return {
        "items": [
            {"candidate_id": r.id, "title": r.title, "url": r.url, "state": r.state}
            for r in session.scalars(
                select(DiscoveryCandidate)
                .where(DiscoveryCandidate.workspace_id == wid)
                .order_by(DiscoveryCandidate.created_at.desc())
                .limit(200)
            )
        ]
    }


@router.post("/plans")
def create(
    body: PlanIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    actor, wid = context(request, session)
    role_required(session, actor, wid, {"engineer"})
    rag.require(len(set(body.candidate_ids)) == len(body.candidate_ids), "INVALID_ARGUMENT")
    row = acquisition.create(
        session,
        request.app.state.config,
        wid,
        actor,
        body.source_id,
        body.candidate_ids,
        body.request_key,
    )
    audit(session, request, wid, actor, "collection.plan.create", "ingest_plan", row.id)
    session.commit()
    return acquisition.serialize(row)


@router.get("/plans")
def plans(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    _, wid = context(request, session)
    return {
        "items": [
            acquisition.serialize(r)
            for r in session.scalars(
                select(IngestPlan)
                .where(IngestPlan.workspace_id == wid)
                .order_by(IngestPlan.created_at.desc())
                .limit(200)
            )
        ]
    }


@router.get("/plans/{plan_id}")
def detail(
    plan_id: str, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    _, wid = context(request, session)
    row = session.scalar(
        select(IngestPlan).where(IngestPlan.id == plan_id, IngestPlan.workspace_id == wid)
    )
    rag.require(row, "NOT_FOUND")
    assert row is not None
    return acquisition.serialize(row)


@router.post("/plans/{plan_id}/review", status_code=202)
def review(
    plan_id: str, body: ReviewIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    actor, wid = context(request, session)
    role_required(session, actor, wid, {"reviewer"})
    row = session.scalar(
        select(IngestPlan)
        .where(IngestPlan.id == plan_id, IngestPlan.workspace_id == wid)
        .with_for_update()
    )
    rag.require(row, "NOT_FOUND")
    assert row is not None
    rag.require(row.status == "draft", "INVALID_STATE_TRANSITION")
    rag.require(row.created_by != actor, "SEPARATION_OF_DUTIES")
    row.reviewed_by = actor
    row.review_note = body.legal_basis
    row.status = "queued" if body.approve else "rejected"
    if body.approve:
        rag.enqueue(session, wid, row.id, "collection.plan.execute")
    audit(session, request, wid, actor, "collection.plan.review", "ingest_plan", row.id)
    session.commit()
    return acquisition.serialize(row)
