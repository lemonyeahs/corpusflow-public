from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.api.v1.business import audit, db, role_required
from corpusflow.api.v1.rag import context
from corpusflow.db.models import ReviewAssignment, ReviewTask
from corpusflow.services import blind_review

router = APIRouter(prefix="/api/v1/review-tasks", tags=["blind-review"])


class CaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str
    generation_id: str | None = None


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=120)
    cases: list[CaseIn] = Field(min_length=1, max_length=20)
    reviewer_ids: list[str] = Field(min_length=2, max_length=5)


class ScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_support: int = Field(ge=0, le=4)
    completeness: int = Field(ge=0, le=4)
    answer_correctness: int | None = Field(default=None, ge=0, le=4)
    unsupported_answer: bool | None = None
    irrelevant: bool
    no_answer_expected: bool
    note: str = Field(min_length=8, max_length=2000)


class ScoresIn(BaseModel):
    scores: list[ScoreIn] = Field(min_length=1, max_length=20)


@router.post("")
def create(body: TaskIn, request: Request, session: Annotated[Session, Depends(db)]) -> Any:
    user, wid = context(request, session)
    role_required(session, user, wid, {"admin"})
    task = blind_review.create(
        session,
        wid,
        user,
        body.request_key,
        [c.model_dump() for c in body.cases],
        body.reviewer_ids,
    )
    audit(session, request, wid, user, "review_task.create", "review_task", task.id)
    session.commit()
    return {"task_id": task.id, "snapshot_sha256": task.snapshot_sha256}


@router.get("")
def tasks(request: Request, session: Annotated[Session, Depends(db)]) -> Any:
    user, wid = context(request, session)
    role_required(session, user, wid, {"admin"})
    return {
        "items": [
            {"task_id": t.id, "snapshot_sha256": t.snapshot_sha256}
            for t in session.scalars(
                select(ReviewTask)
                .where(ReviewTask.workspace_id == wid)
                .order_by(ReviewTask.created_at.desc())
                .limit(200)
            )
        ]
    }


@router.get("/assignments")
def assignments(request: Request, session: Annotated[Session, Depends(db)]) -> Any:
    user, wid = context(request, session)
    blind_review.eligible(session, wid, user)
    return {
        "items": [
            {"assignment_id": a.id, "submitted": bool(blind_review.scores(session, wid, a.id))}
            for a in session.scalars(
                select(ReviewAssignment)
                .join(ReviewTask)
                .where(ReviewAssignment.reviewer_id == user, ReviewTask.workspace_id == wid)
                .limit(200)
            )
        ]
    }


@router.get("/assignments/{aid}")
def detail(aid: str, request: Request, session: Annotated[Session, Depends(db)]) -> Any:
    user, wid = context(request, session)
    result = blind_review.view(session, wid, user, aid)
    audit(session, request, wid, user, "review_assignment.read", "review_assignment", aid)
    session.commit()
    return result


@router.post("/assignments/{aid}/scores")
def submit(
    aid: str, body: ScoresIn, request: Request, session: Annotated[Session, Depends(db)]
) -> Any:
    user, wid = context(request, session)
    blind_review.submit(session, wid, user, aid, [s.model_dump() for s in body.scores])
    audit(session, request, wid, user, "review_assignment.submit", "review_assignment", aid)
    session.commit()
    return {"status": "submitted"}


@router.get("/{tid}/export")
def export(tid: str, request: Request, session: Annotated[Session, Depends(db)]) -> Any:
    user, wid = context(request, session)
    role_required(session, user, wid, {"admin"})
    result = blind_review.export(session, wid, tid)
    audit(session, request, wid, user, "review_task.export", "review_task", tid)
    session.commit()
    return result
