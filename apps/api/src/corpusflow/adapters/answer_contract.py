"""Provider-independent closed-evidence answer validation; not a model implementation."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: str
    quote: str = Field(min_length=1, max_length=4000)


class EvidenceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=16000)
    citations: list[Citation] = Field(min_length=1, max_length=20)


def validate_answer(payload: dict[str, Any], visible_trace: dict[str, Any]) -> EvidenceAnswer:
    """Caller must supply a freshly authorized trace, never a stale browser snapshot."""
    if visible_trace.get("status") != "EVIDENCE_FOUND":
        raise ValueError("ANSWER_EVIDENCE_INSUFFICIENT")
    result = EvidenceAnswer.model_validate(payload)
    hits: dict[str, list[str]] = {}
    for hit in visible_trace.get("hits", []):
        hits.setdefault(hit["segment_id"], []).append(hit["text"])
    for citation in result.citations:
        if citation.segment_id not in hits or not any(
            citation.quote in text for text in hits[citation.segment_id]
        ):
            raise ValueError("ANSWER_CITATION_INVALID")
    return result
