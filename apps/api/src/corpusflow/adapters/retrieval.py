"""Deterministic local lexical retrieval. No semantic/LLM claims."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Protocol

TOKENIZER = "unicode-cjk-bigram-latin-v1"


class EmbeddingProvider(Protocol):
    model_version: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class GenerationProvider(Protocol):
    model_version: str

    def answer(self, query: str, evidence: list[dict[str, str]]) -> dict[str, str]: ...


def tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFKC", value).casefold()
    result = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", value)
    for word in re.findall(r"[\u3400-\u9fff]+", value):
        result.extend([word] if len(word) < 2 else [word[i : i + 2] for i in range(len(word) - 1)])
    return result


def bm25(query: str, documents: dict[str, str]) -> dict[str, float]:
    terms = set(tokens(query))
    counts = {key: Counter(tokens(value)) for key, value in documents.items()}
    lengths = {key: sum(value.values()) for key, value in counts.items()}
    mean = sum(lengths.values()) / max(1, len(counts))
    scores: dict[str, float] = {}
    for term in terms:
        frequency = sum(term in value for value in counts.values())
        idf = math.log(1 + (len(counts) - frequency + 0.5) / (frequency + 0.5))
        for key, value in counts.items():
            tf = value[term]
            if tf:
                scores[key] = scores.get(key, 0) + idf * tf * 2.2 / (
                    tf + 1.2 * (0.25 + 0.75 * lengths[key] / max(mean, 1))
                )
    return scores


def reciprocal_rank(lists: list[list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for values in lists:
        for rank, key in enumerate(values, 1):
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    return scores


def metrics(expected: dict[str, int], retrieved: list[str], k: int) -> dict[str, float | None]:
    # Segment-level relevance: multiple chunks of one segment cannot inflate recall.
    ranked = retrieved[:k]
    unique = list(dict.fromkeys(ranked))
    relevant = {key for key, grade in expected.items() if grade > 0}
    matches = relevant.intersection(unique)
    if not relevant:
        return {
            "recall": None,
            "precision": None,
            "mrr": None,
            "ndcg": None,
            "hit": None,
            "no_answer_correct": float(not retrieved),
        }
    credited: set[str] = set()
    dcg = 0.0
    for i, key in enumerate(ranked):
        if key not in credited:
            dcg += (2 ** expected.get(key, 0) - 1) / math.log2(i + 2)
        credited.add(key)
    ideal = sum(
        (2**grade - 1) / math.log2(i + 2)
        for i, grade in enumerate(sorted(expected.values(), reverse=True)[:k])
    )
    return {
        "recall": len(matches) / len(relevant),
        "precision": len(matches) / k,
        "mrr": next((1 / (i + 1) for i, key in enumerate(ranked) if key in relevant), 0.0),
        "ndcg": dcg / ideal if ideal else 0.0,
        "hit": float(bool(matches)),
        "no_answer_correct": None,
    }
