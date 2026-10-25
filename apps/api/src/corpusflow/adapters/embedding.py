"""Bounded local model protocol. Model identity is frozen in each index."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from corpusflow.core.config import Settings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise EmbeddingError("ADAPTER_REDIRECT_REJECTED")


class EmbeddingError(ValueError):
    pass


class EmbeddingAdapter:
    def __init__(self, settings: Settings):
        self.endpoint = settings.embedding_endpoint.rstrip("/")
        self.timeout = settings.embedding_timeout
        self.retries = settings.embedding_retries

    def call(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.endpoint:
            raise EmbeddingError("ADAPTER_UNAVAILABLE")
        request = Request(
            self.endpoint + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(self.retries + 1):
            try:
                with build_opener(ProxyHandler({}), NoRedirect()).open(
                    request, timeout=self.timeout
                ) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise EmbeddingError("EMBEDDING_RESPONSE_INVALID")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise EmbeddingError("EMBEDDING_RESPONSE_INVALID")
                return result
            except HTTPError as exc:
                raise EmbeddingError(
                    "EMBEDDING_MODEL_MISMATCH" if exc.code == 409 else "ADAPTER_UNAVAILABLE"
                ) from None
            except (URLError, TimeoutError):
                if attempt == self.retries:
                    raise EmbeddingError("ADAPTER_UNAVAILABLE") from None
        raise EmbeddingError("ADAPTER_UNAVAILABLE")

    def profile(self) -> dict[str, Any]:
        info = self.call("/metadata")
        if (
            info.get("provider") != "local-sentence-transformers"
            or not isinstance(info.get("dimensions"), int)
            or not 1 <= info["dimensions"] <= 4096
            or not isinstance(info.get("model_version"), str)
            or len(info["model_version"]) != 64
        ):
            raise EmbeddingError("EMBEDDING_RESPONSE_INVALID")
        return info

    def embed(
        self, texts: list[str], profile: dict[str, Any]
    ) -> tuple[list[list[float]], dict[str, Any]]:
        vectors: list[list[float]] = []
        usage = {"input_tokens": 0, "encoded_tokens": 0, "truncated_inputs": 0}
        for offset in range(0, len(texts), 16):
            batch = texts[offset : offset + 16]
            result = self.call(
                "/embed", {"texts": batch, "model_version": profile["model_version"]}
            )
            if result.get("metadata") != profile:
                raise EmbeddingError("EMBEDDING_MODEL_MISMATCH")
            values = result.get("vectors", [])
            if not isinstance(values, list) or len(values) != len(batch):
                raise EmbeddingError("EMBEDDING_RESPONSE_INVALID")
            for vector in values:
                if (
                    not isinstance(vector, list)
                    or len(vector) != profile["dimensions"]
                    or any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in vector)
                    or not 0.99 < sum(x * x for x in vector) < 1.01
                ):
                    raise EmbeddingError("EMBEDDING_RESPONSE_INVALID")
                vectors.append(vector)
            for key in usage:
                usage[key] += int(result["usage"][key])
        return vectors, {
            **usage,
            "input_sha256": hashlib.sha256(
                json.dumps(texts, ensure_ascii=False).encode()
            ).hexdigest(),
            "external_api_cost": 0,
            "local_compute_cost": "NOT_MEASURED",
            "timeout_seconds": self.timeout,
            "retry_limit": self.retries,
        }


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingError("EMBEDDING_MODEL_MISMATCH")
    return sum(a * b for a, b in zip(left, right, strict=True))
