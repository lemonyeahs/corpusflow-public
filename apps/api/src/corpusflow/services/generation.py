"""Explicit egress scope, durable call budget, freshly reauthorized evidence."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from corpusflow.adapters.answer_contract import validate_answer
from corpusflow.adapters.generation import GenerationAdapter, configuration
from corpusflow.core.config import Settings
from corpusflow.db.models import GenerationRun, RetrievalTrace
from corpusflow.services import rag
from corpusflow.services.quality_governance import lock


def visible(session: Session, wid: str, tid: str) -> dict[str, Any]:
    trace = session.scalar(
        select(RetrievalTrace).where(RetrievalTrace.id == tid, RetrievalTrace.workspace_id == wid)
    )
    rag.require(trace, "NOT_FOUND")
    assert trace is not None
    result = rag.visible_trace(session, wid, trace)
    rag.require(result["redacted_hit_count"] == 0, "PURPOSE_GRANT_MISSING")
    return result


def create(
    session: Session, settings: Settings, wid: str, actor: str, tid: str, key: str
) -> GenerationRun:
    rag.require(wid in settings.llm_workspaces, "GENERATION_EGRESS_NOT_AUTHORIZED")
    lock(session, f"generation:{wid}:{key}")
    trace = visible(session, wid, tid)
    existing = session.scalar(
        select(GenerationRun).where(
            GenerationRun.workspace_id == wid, GenerationRun.request_key == key
        )
    )
    if existing:
        rag.require(
            existing.trace_id == tid and existing.created_by == actor, "IDEMPOTENCY_KEY_REUSED"
        )
        return existing
    row = GenerationRun(
        workspace_id=wid,
        trace_id=tid,
        created_by=actor,
        request_key=key,
        config_snapshot=configuration(settings),
    )
    if trace["status"] != "EVIDENCE_FOUND":
        row.status = "refused"
        row.result = {"reason": "ANSWER_EVIDENCE_INSUFFICIENT", "external_calls": 0}
    session.add(row)
    session.flush()
    if row.status == "queued":
        rag.enqueue(session, wid, row.id, "rag.answer.generate")
    return row


def reserve(session: Session, settings: Settings, row: GenerationRun) -> None:
    # Reservation survives a crash. Unknown outcomes must never automatically incur
    # a second provider charge. The deployment budget includes failures and timeouts.
    lock(session, "generation-global-budget")
    count = (
        session.scalar(
            select(func.count(GenerationRun.id)).where(GenerationRun.call_reserved.is_(True))
        )
        or 0
    )
    rag.require(count < settings.llm_max_calls, "GENERATION_BUDGET_EXHAUSTED")
    rag.require(
        not session.scalar(
            select(GenerationRun.id).where(
                GenerationRun.error_code == "PROVIDER_TOKEN_LIMIT_VIOLATION"
            )
        ),
        "GENERATION_PROVIDER_DISABLED",
    )
    row.call_reserved = True
    row.status = "running"
    session.commit()


def execute(session: Session, settings: Settings, row: GenerationRun) -> None:
    rag.member(session, row.workspace_id, row.created_by, True)
    rag.require(row.workspace_id in settings.llm_workspaces, "GENERATION_EGRESS_NOT_AUTHORIZED")
    rag.require(configuration(settings) == row.config_snapshot, "GENERATION_CONFIG_CHANGED")
    trace = visible(session, row.workspace_id, row.trace_id)
    rag.require(trace["status"] == "EVIDENCE_FOUND", "ANSWER_EVIDENCE_INSUFFICIENT")
    reserve(session, settings, row)
    response = GenerationAdapter(settings).answer(trace)
    # Authorization may change during network I/O: publication checks it again.
    current = visible(session, row.workspace_id, row.trace_id)
    payload = response.pop("payload")
    if isinstance(payload, dict) and set(payload) == {"refusal"}:
        row.status = "refused"
        row.result = {**response, "reason": str(payload["refusal"])[:1000]}
    else:
        answer = validate_answer(payload, current)
        row.result = {
            **response,
            **answer.model_dump(),
            "evidence_trace_id": row.trace_id,
            "semantic_faithfulness": "REQUIRES_HUMAN_REVIEW",
        }
        row.status = "succeeded"


def report(session: Session, wid: str, row: GenerationRun) -> dict[str, Any]:
    rag.require(row.workspace_id == wid, "NOT_FOUND")
    visible(session, wid, row.trace_id)
    return {
        "generation_id": row.id,
        "trace_id": row.trace_id,
        "status": row.status,
        "config": row.config_snapshot,
        "result": row.result,
        "error_code": row.error_code,
        "call_reserved": row.call_reserved,
    }
