"""Real offline model; explicitly configured local service required."""

import os

import pytest
from corpusflow.adapters.embedding import EmbeddingAdapter, EmbeddingError, cosine
from corpusflow.core.config import load_settings


@pytest.mark.integration
def test_real_multilingual_embeddings_and_model_identity():
    if not os.environ.get("EMBEDDING_ENDPOINT"):
        pytest.skip("Explicit local embedding endpoint required")
    adapter = EmbeddingAdapter(load_settings())
    profile = adapter.profile()
    vectors, usage = adapter.embed(["密钥轮换", "更换加密密钥", "一杯咖啡"], profile)
    assert len(vectors[0]) == profile["dimensions"] == 384
    assert cosine(vectors[0], vectors[1]) > cosine(vectors[0], vectors[2]) + 0.2
    assert usage["input_tokens"] > 0 and usage["external_api_cost"] == 0
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL_MISMATCH"):
        adapter.embed(["AES"], {**profile, "model_version": "0" * 64})
