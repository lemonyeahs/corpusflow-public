"""Typed RAG endpoints. Authentication and reviews reuse existing boundaries."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.api.v1.business import actor_id, audit, db, role_required, workspace_id
from corpusflow.db.models import (
    Dataset,
    DatasetVersion,
    QualityIssue,
    RagEvaluationRun,
    RagEvaluationSuite,
    RagFeedback,
    RagIndexVersion,
    RetrievalTrace,
    uid,
)
from corpusflow.services import rag
from corpusflow.services.quality_governance import lock

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


class IndexIn(BaseModel):
    embedding: bool = False
    dataset_version_id: str
    request_key: str = Field(min_length=1, max_length=120)


class QueryIn(BaseModel):
    index_version_id: str
    query: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    strategy: Literal["fts", "bm25", "hybrid", "vector", "semantic_hybrid"] = "bm25"
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = False
    min_similarity: float = Field(default=0.5, ge=-1, le=1)


class SuiteIn(BaseModel):
    dataset_version_id: str
    name: str = Field(min_length=1, max_length=160)
    annotation_note: str = Field(min_length=8, max_length=2000)
    no_answer_queries: list[str] = Field(default_factory=list, max_length=20)


class EvalIn(BaseModel):
    suite_id: str
    index_version_id: str
    request_key: str = Field(min_length=1, max_length=120)
    strategy: Literal["fts", "bm25", "hybrid", "vector", "semantic_hybrid"] = "bm25"
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = False
    min_similarity: float = Field(default=0.5, ge=-1, le=1)


class FeedbackIn(BaseModel):
    trace_id: str
    segment_id: str
    evaluation_run_id: str | None = None
    case_id: str | None = None
    category: Literal[
        "source", "parser", "cleaning", "chunk", "lineage", "retrieval", "reranker", "generation"
    ]
    note: str = Field(min_length=3, max_length=2000)


def context(request: Request, session: Session) -> tuple[str, str]:
    user = actor_id(request, session)
    return user, workspace_id(request, session, user)


def index_json(row: RagIndexVersion) -> dict[str, Any]:
    return {
        "index_version_id": row.id,
        "dataset_version_id": row.dataset_version_id,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "config": row.config,
        "content_sha256": row.content_sha256,
        "error_code": row.error_code,
    }


@router.get("/capabilities")
def capabilities(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    context(request, session)
    return {
        "strategies": ["fts", "bm25", "hybrid", "vector", "semantic_hybrid"],
        "vector": "CONFIGURED_NOT_PROBED"
        if request.app.state.config.embedding_endpoint
        else "NOT_CONFIGURED",
        "generation": "NOT_CONFIGURED",
        "reranker": "token-coverage-v1",
        "scope": "bounded PostgreSQL exact cosine; local model requires configuration",
        "max_chunks": 5000,
    }


@router.get("/versions")
def versions(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    _, wid = context(request, session)
    rows = session.execute(
        select(DatasetVersion, Dataset.product_type)
        .join(Dataset)
        .where(
            DatasetVersion.workspace_id == wid,
            DatasetVersion.status == "published",
            Dataset.product_type.in_(["rag", "evaluation"]),
        )
        .order_by(DatasetVersion.created_at.desc())
        .limit(200)
    ).all()
    return {
        "items": [
            {
                "dataset_version_id": v.id,
                "dataset_id": v.dataset_id,
                "version": v.version,
                "product_type": p,
            }
            for v, p in rows
        ]
    }


@router.post("/indexes", status_code=202)
def create_index(
    body: IndexIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    user, wid = context(request, session)
    role_required(session, user, wid, {"engineer"})
    row = rag.create_index(
        session,
        wid,
        user,
        body.dataset_version_id,
        body.request_key,
        body.embedding,
        request.app.state.config,
    )
    audit(session, request, wid, user, "rag.index.create", "rag_index", row.id)
    session.commit()
    return index_json(row)


@router.get("/indexes")
def indexes(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    _, wid = context(request, session)
    return {
        "items": [
            index_json(row)
            for row in session.scalars(
                select(RagIndexVersion)
                .where(RagIndexVersion.workspace_id == wid)
                .order_by(RagIndexVersion.created_at.desc())
                .limit(200)
            )
        ]
    }


@router.get("/indexes/{index_id}")
def index_detail(
    index_id: str, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    _, wid = context(request, session)
    row = session.scalar(
        select(RagIndexVersion).where(
            RagIndexVersion.workspace_id == wid, RagIndexVersion.id == index_id
        )
    )
    rag.require(row, "NOT_FOUND")
    assert row is not None
    return index_json(row)


@router.post("/queries")
def query(
    body: QueryIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    user, wid = context(request, session)
    trace = rag.retrieve(
        session,
        wid,
        user,
        body.index_version_id,
        body.query,
        body.strategy,
        body.top_k,
        body.rerank,
        body.min_similarity,
        request.app.state.config,
    )
    audit(
        session,
        request,
        wid,
        user,
        "rag.query",
        "retrieval_trace",
        trace.id,
        {"index_version_id": body.index_version_id, "hit_count": len(trace.result["hits"])},
    )
    result = rag.visible_trace(session, wid, trace)
    session.commit()
    return result


@router.get("/traces/{trace_id}")
def trace_detail(
    trace_id: str, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    user, wid = context(request, session)
    row = session.scalar(
        select(RetrievalTrace).where(
            RetrievalTrace.workspace_id == wid, RetrievalTrace.id == trace_id
        )
    )
    rag.require(row, "NOT_FOUND")
    assert row is not None
    result = rag.visible_trace(session, wid, row)
    audit(session, request, wid, user, "rag.trace.read", "retrieval_trace", row.id)
    session.commit()
    return result


@router.post("/suites")
def create_suite(
    body: SuiteIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    user, wid = context(request, session)
    role_required(session, user, wid, {"reviewer"})
    rag.require(all(0 < len(q.strip()) <= 2000 for q in body.no_answer_queries), "INVALID_ARGUMENT")
    row = rag.create_suite(
        session,
        request.app.state.config,
        wid,
        user,
        body.dataset_version_id,
        body.name,
        body.annotation_note,
        body.no_answer_queries,
    )
    audit(session, request, wid, user, "rag.suite.create", "rag_suite", row.id)
    session.commit()
    return {"suite_id": row.id, "case_count": len(row.cases), "sha256": row.content_sha256}


@router.get("/suites")
def suites(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    _, wid = context(request, session)
    return {
        "items": [
            {
                "suite_id": s.id,
                "name": s.name,
                "case_count": len(s.cases),
                "sha256": s.content_sha256,
                "reviewed_by": s.reviewed_by,
                "annotation_note": s.annotation_note,
            }
            for s in session.scalars(
                select(RagEvaluationSuite).where(RagEvaluationSuite.workspace_id == wid).limit(200)
            )
        ]
    }


@router.post("/evaluations", status_code=202)
def create_eval(
    body: EvalIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    user, wid = context(request, session)
    role_required(session, user, wid, {"engineer"})
    lock(session, f"rag-eval:{wid}:{body.request_key}")
    suite = session.scalar(
        select(RagEvaluationSuite)
        .where(RagEvaluationSuite.workspace_id == wid, RagEvaluationSuite.id == body.suite_id)
        .with_for_update()
    )
    rag.require(suite, "NOT_FOUND")
    rag.allowed_chunks(session, wid, body.index_version_id)
    config = {
        "strategy": body.strategy,
        "top_k": body.top_k,
        "rerank": body.rerank,
        "min_similarity": body.min_similarity,
    }
    row = session.scalar(
        select(RagEvaluationRun).where(
            RagEvaluationRun.workspace_id == wid, RagEvaluationRun.request_key == body.request_key
        )
    )
    if row:
        rag.require(
            row.suite_id == body.suite_id
            and row.index_version_id == body.index_version_id
            and row.config == config,
            "IDEMPOTENCY_KEY_REUSED",
        )
    else:
        row = RagEvaluationRun(
            id=uid(),
            workspace_id=wid,
            suite_id=body.suite_id,
            index_version_id=body.index_version_id,
            created_by=user,
            request_key=body.request_key,
            config=config,
        )
        session.add(row)
        session.flush()
        rag.enqueue(session, wid, row.id, "rag.evaluation.execute")
    audit(session, request, wid, user, "rag.eval.create", "rag_evaluation", row.id)
    session.commit()
    return {"evaluation_id": row.id, "status": row.status}


@router.get("/evaluations")
def evaluation_history(
    request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    _, wid = context(request, session)
    rows = session.scalars(
        select(RagEvaluationRun)
        .where(RagEvaluationRun.workspace_id == wid)
        .order_by(RagEvaluationRun.created_at.desc())
        .limit(100)
    )
    return {
        "items": [
            {
                "evaluation_id": row.id,
                "status": row.status,
                "report": row.report,
                "error_code": row.error_code,
            }
            for row in rows
        ]
    }


@router.get("/evaluations/{evaluation_id}")
def eval_detail(
    evaluation_id: str, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    _, wid = context(request, session)
    row = session.scalar(
        select(RagEvaluationRun).where(
            RagEvaluationRun.workspace_id == wid, RagEvaluationRun.id == evaluation_id
        )
    )
    rag.require(row, "NOT_FOUND")
    assert row is not None
    # Reports contain metric values and IDs, not revoked query evidence text.
    return {
        "evaluation_id": row.id,
        "status": row.status,
        "report": row.report,
        "error_code": row.error_code,
    }


@router.post("/feedback")
def feedback(
    body: FeedbackIn, request: Request, session: Annotated[Session, Depends(db)]
) -> dict[str, Any]:
    user, wid = context(request, session)
    role_required(session, user, wid, {"engineer", "reviewer"})
    trace = session.scalar(
        select(RetrievalTrace).where(
            RetrievalTrace.workspace_id == wid, RetrievalTrace.id == body.trace_id
        )
    )
    rag.require(trace, "NOT_FOUND")
    assert trace is not None
    eligible = {h["segment_id"] for h in rag.visible_trace(session, wid, trace)["hits"]}
    if body.evaluation_run_id:
        evaluation = session.scalar(
            select(RagEvaluationRun).where(
                RagEvaluationRun.workspace_id == wid, RagEvaluationRun.id == body.evaluation_run_id
            )
        )
        rag.require(evaluation and evaluation.status == "succeeded", "NOT_FOUND")
        assert evaluation is not None
        case = next(
            (
                c
                for c in evaluation.report["cases"]
                if c["case_id"] == body.case_id and c["trace_id"] == trace.id
            ),
            None,
        )
        rag.require(case, "INVALID_SAMPLE_EVIDENCE")
        suite = session.get(RagEvaluationSuite, evaluation.suite_id)
        assert suite is not None
        eligible.update(next(c["relevance"] for c in suite.cases if c["case_id"] == body.case_id))
    rag.require(body.segment_id in eligible, "INVALID_SAMPLE_EVIDENCE")
    asset = rag.source_asset(session, wid, body.segment_id)
    rag.require(rag.permitted(session, wid, asset.id, "rag"), "PURPOSE_GRANT_MISSING")
    issue = rag.feedback_issue(session, wid, body.segment_id, body.category, body.note)
    row = RagFeedback(
        workspace_id=wid,
        trace_id=trace.id,
        segment_id=body.segment_id,
        evaluation_run_id=body.evaluation_run_id,
        case_id=body.case_id,
        quality_issue_id=issue.id,
        category=body.category,
        note=body.note,
        created_by=user,
    )
    session.add(row)
    session.flush()
    audit(
        session,
        request,
        wid,
        user,
        "rag.feedback.create",
        "rag_feedback",
        row.id,
        {"trace_id": trace.id, "quality_issue_id": issue.id},
    )
    session.commit()
    return {
        "feedback_id": row.id,
        "quality_issue_id": issue.id,
        "run_id": issue.run_id,
        "status": issue.status,
    }


@router.get("/feedback")
def feedback_list(request: Request, session: Annotated[Session, Depends(db)]) -> dict[str, Any]:
    _, wid = context(request, session)
    rows = session.execute(
        select(RagFeedback, QualityIssue)
        .join(QualityIssue, QualityIssue.id == RagFeedback.quality_issue_id)
        .where(RagFeedback.workspace_id == wid)
        .order_by(RagFeedback.created_at.desc())
        .limit(200)
    )
    return {
        "items": [
            {
                "feedback_id": f.id,
                "trace_id": f.trace_id,
                "segment_id": f.segment_id,
                "quality_issue_id": q.id,
                "status": q.status,
                "run_id": q.run_id,
                "category": f.category,
                "note": f.note,
            }
            for f, q in rows
        ]
    }
