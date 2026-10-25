"""Immutable reviews over currently authorized evidence, preserving individual disagreement."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.db.models import GenerationRun, RetrievalReview, RetrievalTrace
from corpusflow.services import rag
from corpusflow.services.quality_governance import lock


def trace_for_review(session: Session, wid: str, tid: str) -> RetrievalTrace:
    trace = session.scalar(
        select(RetrievalTrace).where(RetrievalTrace.workspace_id == wid, RetrievalTrace.id == tid)
    )
    rag.require(trace, "NOT_FOUND")
    assert trace is not None
    visible = rag.visible_trace(session, wid, trace)
    rag.require(not visible["redacted_hit_count"], "PURPOSE_GRANT_MISSING")
    return trace


def submit(
    session: Session,
    wid: str,
    reviewer: str,
    tid: str,
    key: str,
    ratings: dict[str, Any],
    note: str,
) -> RetrievalReview:
    # Newly optional answer fields must not invalidate old retrieval-only request keys.
    ratings = {key: value for key, value in ratings.items() if value is not None}
    lock(session, f"retrieval-review:{wid}:{key}")
    trace_for_review(session, wid, tid)
    if ratings.get("generation_id"):
        answer = session.scalar(
            select(GenerationRun).where(
                GenerationRun.id == ratings["generation_id"],
                GenerationRun.workspace_id == wid,
                GenerationRun.trace_id == tid,
                GenerationRun.status.in_(["succeeded", "refused"]),
            )
        )
        rag.require(answer, "NOT_FOUND")
        rag.require(ratings.get("answer_correctness") is not None, "INVALID_ARGUMENT")
    else:
        rag.require(
            ratings.get("answer_correctness") is None and ratings.get("unsupported_answer") is None,
            "INVALID_ARGUMENT",
        )
    existing = session.scalar(
        select(RetrievalReview).where(
            RetrievalReview.workspace_id == wid, RetrievalReview.request_key == key
        )
    )
    if existing:
        rag.require(
            existing.trace_id == tid
            and existing.reviewer_id == reviewer
            and {key: value for key, value in existing.ratings.items() if value is not None}
            == ratings
            and existing.note == note,
            "IDEMPOTENCY_KEY_REUSED",
        )
        return existing
    row = RetrievalReview(
        workspace_id=wid,
        trace_id=tid,
        reviewer_id=reviewer,
        request_key=key,
        ratings=ratings,
        note=note,
    )
    session.add(row)
    session.flush()
    return row


def report(session: Session, wid: str, tid: str) -> dict[str, Any]:
    trace_for_review(session, wid, tid)
    rows = session.scalars(
        select(RetrievalReview)
        .where(RetrievalReview.workspace_id == wid, RetrievalReview.trace_id == tid)
        .order_by(RetrievalReview.created_at, RetrievalReview.id)
    ).all()
    latest = {row.reviewer_id: row for row in rows if not row.ratings.get("generation_id")}
    answers = {
        str(row.ratings["generation_id"]) for row in rows if row.ratings.get("generation_id")
    }
    scores = [row.ratings["evidence_support"] for row in latest.values()]
    return {
        "trace_id": tid,
        "rubric_version": "evidence-review.v1",
        "scope": "individual retrieval/answer assessments; not verified expert judgments",
        "answer_reviews": [
            {
                "generation_id": aid,
                "ratings": [
                    {"reviewer_id": r.reviewer_id, **r.ratings}
                    for r in rows
                    if r.ratings.get("generation_id") == aid
                ],
            }
            for aid in sorted(answers)
        ],
        "reviewer_count": len(latest),
        "annotation_count": len(rows),
        "support_range": [min(scores), max(scores)] if scores else None,
        "disagreement": max(scores) - min(scores) if scores else None,
        "items": [
            {
                "review_id": r.id,
                "reviewer_id": r.reviewer_id,
                "ratings": r.ratings,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "expert_credentials": "NOT_VERIFIED",
    }
