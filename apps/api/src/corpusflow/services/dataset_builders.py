"""Product-specific candidate builders behind the shared dataset workflow."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

from corpusflow.db.models import Segment

TOKENIZER_VERSION = "builtin-whitespace-1"


class BuilderError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BuiltCandidate:
    key: str
    payload: dict[str, Any]
    source_id: str
    evidence_ids: list[str]
    excluded_reason: str | None = None


@dataclass(frozen=True)
class BuildResult:
    candidates: list[BuiltCandidate]
    excluded: list[dict[str, str]]
    metrics: dict[str, Any]


class DatasetBuilder(Protocol):
    product_type: str
    purpose: str

    def build(self, segments: list[Segment], config: dict[str, Any]) -> BuildResult: ...


def _tokens(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _segment_order(segment: Segment) -> tuple[int, int, str]:
    location = segment.location_json or {}
    return (
        int(location.get("page", 0) or 0),
        int(location.get("line", 0) or 0),
        segment.id,
    )


def _allowed_segments(
    segments: list[Segment], config: dict[str, Any]
) -> tuple[list[Segment], list[dict[str, str]], set[str]]:
    min_chars = int(config.get("min_chars", 1))
    max_chars = int(config.get("max_chars", 0))
    seen: set[str] = set()
    selected: list[Segment] = []
    excluded: list[dict[str, str]] = []
    for segment in sorted(segments, key=_segment_order):
        text = segment.text.strip()
        if len(text) < min_chars:
            excluded.append({"segment_id": segment.id, "reason": "below_min_chars"})
            continue
        if max_chars and len(text) > max_chars:
            excluded.append({"segment_id": segment.id, "reason": "above_max_chars"})
            continue
        if segment.content_hash in seen:
            excluded.append({"segment_id": segment.id, "reason": "duplicate_content"})
            continue
        seen.add(segment.content_hash)
        selected.append(segment)
    return selected, excluded, seen


class PretrainBuilder:
    product_type = "pretrain"
    purpose = "training"

    def build(self, segments: list[Segment], config: dict[str, Any]) -> BuildResult:
        selected, excluded, _ = _allowed_segments(segments, config)
        groups: dict[str, list[Segment]] = defaultdict(list)
        for segment in selected:
            groups[segment.source_id].append(segment)
        candidates: list[BuiltCandidate] = []
        for source_id, source_segments in sorted(groups.items()):
            text = "\n\n".join(item.text.strip() for item in source_segments)
            if not text:
                excluded.append({"source_id": source_id, "reason": "empty_text"})
                continue
            evidence_ids = [item.id for item in source_segments]
            candidates.append(
                BuiltCandidate(
                    key=f"pretrain:{source_id}",
                    source_id=source_id,
                    evidence_ids=evidence_ids,
                    payload={
                        "text": text,
                        "evidence_ids": evidence_ids,
                        "metadata": {
                            "product_type": "pretrain",
                            "source_id": source_id,
                            "segment_ids": evidence_ids,
                            "tokenizer_version": TOKENIZER_VERSION,
                        },
                    },
                )
            )
        return BuildResult(
            candidates=candidates,
            excluded=excluded,
            metrics={
                "product_type": self.product_type,
                "tokenizer_version": TOKENIZER_VERSION,
                "input_segments": len(segments),
                "candidate_count": len(candidates),
                "excluded_count": len(excluded),
            },
        )


class SftBuilder:
    product_type = "sft"
    purpose = "training"

    def build(self, segments: list[Segment], config: dict[str, Any]) -> BuildResult:
        selected, excluded, _ = _allowed_segments(segments, config)
        candidates = [
            BuiltCandidate(
                key=f"sft:{segment.id}",
                source_id=segment.source_id,
                evidence_ids=[segment.id],
                payload={
                    "messages": [{"role": "user", "content": segment.text}],
                    "evidence_ids": [segment.id],
                },
            )
            for segment in selected
        ]
        return BuildResult(
            candidates=candidates,
            excluded=excluded,
            metrics={
                "product_type": self.product_type,
                "input_segments": len(segments),
                "candidate_count": len(candidates),
                "excluded_count": len(excluded),
            },
        )


class RagDatasetBuilder:
    product_type = "rag"
    purpose = "rag"

    def build(self, segments: list[Segment], config: dict[str, Any]) -> BuildResult:
        selected, excluded, _ = _allowed_segments(segments, config)
        unit = str(config.get("unit", "tokens"))
        chunk_size = int(config.get("chunk_size", 128))
        overlap = int(config.get("overlap", 16))
        if unit not in {"tokens", "chars"}:
            raise BuilderError("INVALID_CHUNK_UNIT", "unit must be tokens or chars")
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise BuilderError("INVALID_CHUNK_CONFIG", "chunk_size must exceed overlap")
        candidates: list[BuiltCandidate] = []
        for segment in selected:
            parts = _tokens(segment.text) if unit == "tokens" else list(segment.text)
            start = 0
            index = 0
            while start < len(parts):
                end = min(start + chunk_size, len(parts))
                chunk = (
                    " ".join(parts[start:end])
                    if unit == "tokens"
                    else "".join(parts[start:end])
                )
                if len(chunk.strip()) >= int(config.get("min_chunk_chars", 1)):
                    candidates.append(
                        BuiltCandidate(
                            key=f"rag:{segment.id}:{index}",
                            source_id=segment.source_id,
                            evidence_ids=[segment.id],
                            payload={
                                "text": chunk,
                                "evidence_ids": [segment.id],
                                "source_id": segment.source_id,
                                "segment_id": segment.id,
                                "document_version_id": segment.document_version_id,
                                "location": segment.location_json or {},
                                "section_title": segment.section_title,
                                "chunk_index": index,
                                "chunk_size": chunk_size,
                                "overlap": overlap,
                                "unit": unit,
                                "tokenizer_version": TOKENIZER_VERSION,
                                "metadata": {"product_type": "rag"},
                            },
                        )
                    )
                index += 1
                if end == len(parts):
                    break
                start = end - overlap
        hashes = [hashlib.sha256(item.payload["text"].encode()).hexdigest() for item in candidates]
        duplicate_count = len(hashes) - len(set(hashes))
        return BuildResult(
            candidates=candidates,
            excluded=excluded,
            metrics={
                "product_type": self.product_type,
                "unit": unit,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "tokenizer_version": TOKENIZER_VERSION,
                "input_segments": len(segments),
                "candidate_count": len(candidates),
                "duplicate_chunk_count": duplicate_count,
                "excluded_count": len(excluded),
            },
        )


class EvaluationDatasetBuilder:
    product_type = "evaluation"
    purpose = "evaluation"

    def build(self, segments: list[Segment], config: dict[str, Any]) -> BuildResult:
        by_id = {segment.id: segment for segment in segments}
        raw_samples = config.get("evaluation_samples", [])
        if not isinstance(raw_samples, list):
            raise BuilderError("INVALID_EVALUATION_CONFIG", "evaluation_samples must be a list")
        candidates: list[BuiltCandidate] = []
        excluded: list[dict[str, str]] = []
        seen_questions: set[str] = set()
        for index, raw in enumerate(raw_samples):
            if not isinstance(raw, dict):
                excluded.append({"sample": str(index), "reason": "invalid_schema"})
                continue
            question = str(raw.get("question", "")).strip()
            reference = str(raw.get("reference_answer", "")).strip()
            evidence_ids = [str(item) for item in raw.get("evidence_ids", []) if str(item) in by_id]
            reasons: list[str] = []
            if not question:
                reasons.append("question_missing")
            if not reference:
                reasons.append("reference_answer_missing")
            if not evidence_ids:
                reasons.append("evidence_missing")
            if question in seen_questions:
                reasons.append("duplicate_question")
            seen_questions.add(question)
            if reasons:
                excluded.append({"sample": str(index), "reason": ",".join(reasons)})
                continue
            source_ids = sorted({by_id[item].source_id for item in evidence_ids})
            candidates.append(
                BuiltCandidate(
                    key=f"evaluation:{index}:{hashlib.sha256(question.encode()).hexdigest()[:12]}",
                    source_id=source_ids[0],
                    evidence_ids=evidence_ids,
                    payload={
                        "question": question,
                        "reference_answer": reference,
                        "evidence_ids": evidence_ids,
                        "question_type": str(raw.get("question_type", "open")),
                        "difficulty": str(raw.get("difficulty", "medium")),
                        "domain": str(raw.get("domain", "general")),
                        "source_ids": source_ids,
                        "review_status": "pending",
                        "quality_status": "pending",
                    },
                )
            )
        return BuildResult(
            candidates=candidates,
            excluded=excluded,
            metrics={
                "product_type": self.product_type,
                "input_segments": len(segments),
                "candidate_count": len(candidates),
                "excluded_count": len(excluded),
                "duplicate_question_count": sum(
                    "duplicate_question" in item["reason"] for item in excluded
                ),
            },
        )


BUILDERS: dict[str, DatasetBuilder] = {
    "sft": SftBuilder(),
    "pretrain": PretrainBuilder(),
    "rag": RagDatasetBuilder(),
    "evaluation": EvaluationDatasetBuilder(),
}


def builder_for(product_type: str) -> DatasetBuilder | None:
    return BUILDERS.get(product_type)

