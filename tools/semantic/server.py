"""Loopback-only offline embedding service. Never downloads weights or logs input text."""

import hashlib
import os
from pathlib import Path
from threading import Lock

import sentence_transformers
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
model_dir = Path(os.environ["CF_EMBEDDING_MODEL_DIR"]).resolve(strict=True)
model = SentenceTransformer(str(model_dir), local_files_only=True, device="cpu")
model_lock = Lock()
identity = hashlib.sha256()
for path in sorted(model_dir.rglob("*")):
    if path.is_file() and path.suffix in {".json", ".txt", ".safetensors"}:
        identity.update(str(path.relative_to(model_dir)).encode())
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                identity.update(block)
metadata = {
    "provider": "local-sentence-transformers",
    "model": "paraphrase-multilingual-MiniLM-L12-v2",
    "model_version": identity.hexdigest(),
    "runtime_version": sentence_transformers.__version__,
    "dimensions": model.get_sentence_embedding_dimension(),
    "max_tokens": model.max_seq_length,
    "normalization": "l2",
    "device": "cpu",
    "batch_size": 16,
}
app = FastAPI()


class Input(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=16)
    model_version: str


@app.get("/metadata")
def info():
    return metadata


@app.post("/embed")
def embed(body: Input):
    if body.model_version != metadata["model_version"]:
        raise HTTPException(409, "EMBEDDING_MODEL_MISMATCH")
    if any(not text.strip() or len(text) > 100_000 for text in body.texts):
        raise HTTPException(422, "EMBEDDING_INPUT_INVALID")
    with model_lock:
        vectors = model.encode(body.texts, normalize_embeddings=True, batch_size=16).tolist()
        counts = [len(model.tokenizer.encode(text, truncation=False)) for text in body.texts]
    return {
        "metadata": metadata,
        "vectors": vectors,
        "usage": {
            "input_tokens": sum(counts),
            "encoded_tokens": sum(min(n, model.max_seq_length) for n in counts),
            "truncated_inputs": sum(n > model.max_seq_length for n in counts),
            "external_api_cost": 0,
            "local_compute_cost": "NOT_MEASURED",
        },
    }
