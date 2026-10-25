"""Hand-calculated metric oracles and real lexical computations."""

import math

import pytest
from corpusflow.adapters.retrieval import bm25, metrics, reciprocal_rank, tokens
from corpusflow.api.v1.rag import QueryIn
from pydantic import ValidationError


def test_unicode_tokenization_and_distinct_queries():
    docs = {"a": "AES 密钥轮换 128 bits", "b": "SHA-256 message digest", "c": "Merkle root"}
    assert "密钥" in tokens(docs["a"])
    assert max(bm25("AES 密钥", docs), key=bm25("AES 密钥", docs).get) == "a"
    assert set(bm25("Merkle", docs)) == {"c"}
    assert bm25("quantumunicorn", docs) == {}
    assert "sha-256" in tokens(docs["b"])


def test_real_scores_change_with_corpus_frequency():
    single = bm25("AES", {"a": "AES AES AES", "b": "Merkle"})["a"]
    common = bm25("AES", {"a": "AES AES AES", "b": "AES"})["a"]
    assert single > common > 0


def test_metrics_hand_calculated():
    values = metrics({"a": 3, "b": 1}, ["x", "a", "b"], 3)
    assert values["recall"] == 1
    assert values["precision"] == pytest.approx(2 / 3)
    assert values["mrr"] == 0.5
    assert values["ndcg"] == pytest.approx((7 / math.log2(3) + 1 / 2) / (7 + 1 / math.log2(3)))
    assert values["hit"] == 1


def test_duplicates_do_not_inflate_metrics_or_compress_rank():
    m = metrics({"a": 1}, ["x", "x", "a"], 3)
    assert m["mrr"] == pytest.approx(1 / 3)
    assert m["precision"] == pytest.approx(1 / 3)
    assert m["ndcg"] == 0.5
    m2 = metrics({"a": 1}, ["a", "a", "a"], 3)
    assert m2["ndcg"] == 1
    assert m2["recall"] == 1
    assert m2["precision"] == pytest.approx(1 / 3)


def test_no_answer_is_separate_population():
    assert metrics({}, [], 3)["no_answer_correct"] == 1
    assert metrics({}, ["x"], 3)["no_answer_correct"] == 0
    assert metrics({}, [], 3)["recall"] is None
    assert metrics({"a": 1}, [], 3)["recall"] == 0


def test_rrf_is_not_a_probability():
    scores = reciprocal_rank([["a", "b"], ["b", "a"]])
    assert scores["a"] == scores["b"] == pytest.approx(1 / 61 + 1 / 62)


@pytest.mark.parametrize("query,k", [(" ", 3), ("", 3), ("AES", 0), ("AES", 51)])
def test_input_limits(query, k):
    with pytest.raises(ValidationError):
        QueryIn(index_version_id="i", query=query, top_k=k)
