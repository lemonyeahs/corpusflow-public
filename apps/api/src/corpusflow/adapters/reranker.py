"""Real local bi-encoder reranking baseline; NOT a cross-encoder relevance model."""

from typing import Any

from corpusflow.adapters.embedding import EmbeddingAdapter, cosine
from corpusflow.core.config import Settings


class RerankerAdapter:
    def __init__(self, settings: Settings):
        self.embedding = EmbeddingAdapter(settings)

    def rerank(
        self, query: str, documents: dict[str, str]
    ) -> tuple[dict[str, float], dict[str, Any]]:
        profile = self.embedding.profile()
        vectors, usage = self.embedding.embed([query, *documents.values()], profile)
        scores = {
            key: cosine(vectors[0], vector)
            for key, vector in zip(documents, vectors[1:], strict=True)
        }
        return scores, {
            "kind": "bi-encoder-cosine.v1",
            "model": profile,
            "usage": usage,
            "candidate_count": len(documents),
            "cross_encoder": False,
        }
