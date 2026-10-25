"""Workspace-scoped RAG application service, shared by API and worker.

Indexes and traces are bounded development workloads (max 5000 chunks). All
consumption rechecks the current purpose grant, including historical traces.
"""

from __future__ import annotations

import hashlib
import math
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from corpusflow.adapters.embedding import EmbeddingAdapter, cosine
from corpusflow.adapters.retrieval import TOKENIZER, bm25, metrics, reciprocal_rank, tokens
from corpusflow.core.config import Settings, load_settings
from corpusflow.db.models import (
    Asset,
    CandidateSample,
    Dataset,
    DatasetVersion,
    Document,
    DocumentVersion,
    LicenseEvidence,
    LicenseGrant,
    LineageEdge,
    Membership,
    OutboxEvent,
    PipelineRun,
    QualityIssue,
    RagChunk,
    RagEvaluationRun,
    RagEvaluationSuite,
    RagIndexVersion,
    RetrievalTrace,
    SampleEvidence,
    Segment,
    User,
    uid,
)
from corpusflow.services.quality_governance import digest, lock, read_release


class RagError(ValueError):
    pass


def require(condition: Any, code: str) -> None:
    if not condition:
        raise RagError(code)


def member(session: Session, wid: str, actor: str, writer: bool = False) -> None:
    role = session.scalar(
        select(Membership.role)
        .join(User, User.id == Membership.user_id)
        .where(
            User.disabled.is_(False),
            Membership.workspace_id == wid,
            Membership.user_id == actor,
            Membership.status == "active",
        )
    )
    require(
        role
        in (
            {"admin", "engineer"}
            if writer
            else {"admin", "engineer", "reviewer", "reader", "viewer"}
        ),
        "PERMISSION_DENIED",
    )


def permitted(session: Session, wid: str, asset_id: str, purpose: str) -> bool:
    asset = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == wid))
    if not asset:
        return False
    grant = session.scalar(
        select(LicenseGrant)
        .where(
            LicenseGrant.workspace_id == wid,
            LicenseGrant.asset_id == asset_id,
            LicenseGrant.purpose == purpose,
        )
        .order_by(LicenseGrant.created_at.desc(), LicenseGrant.id)
    )
    return bool(
        grant
        and grant.status == "confirmed"
        and session.scalar(
            select(LicenseEvidence.id).where(
                LicenseEvidence.id == grant.evidence_id,
                LicenseEvidence.workspace_id == wid,
                LicenseEvidence.asset_id == asset_id,
            )
        )
    )


def source_asset(session: Session, wid: str, segment_id: str) -> Asset:
    asset = session.scalar(
        select(Asset)
        .join(Document, Document.asset_id == Asset.id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(Segment, Segment.document_version_id == DocumentVersion.id)
        .where(
            Segment.id == segment_id,
            Segment.workspace_id == wid,
            DocumentVersion.workspace_id == wid,
            Document.workspace_id == wid,
            Asset.workspace_id == wid,
        )
    )
    require(asset, "INVALID_SAMPLE_EVIDENCE")
    assert asset is not None
    return asset


def version(session: Session, wid: str, vid: str, product: str) -> DatasetVersion:
    row = session.scalar(
        select(DatasetVersion)
        .join(Dataset)
        .where(
            DatasetVersion.id == vid,
            DatasetVersion.workspace_id == wid,
            Dataset.product_type == product,
            DatasetVersion.status == "published",
        )
    )
    require(row, "NOT_FOUND")
    assert row is not None
    return row


def enqueue(session: Session, wid: str, object_id: str, kind: str) -> None:
    session.add(
        OutboxEvent(
            workspace_id=wid,
            aggregate_type=kind,
            aggregate_id=object_id,
            event_type=kind,
            payload={"id": object_id},
        )
    )


def create_index(
    session: Session,
    wid: str,
    actor: str,
    vid: str,
    key: str,
    embedding: bool = False,
    settings: Settings | None = None,
) -> RagIndexVersion:
    lock(session, f"rag-index:{wid}:{key}")
    # Lock parent to serialize repeated requests and construction revisions.
    session.execute(
        select(DatasetVersion.id)
        .where(DatasetVersion.id == vid, DatasetVersion.workspace_id == wid)
        .with_for_update()
    ).first()
    v = version(session, wid, vid, "rag")
    existing = session.scalar(
        select(RagIndexVersion).where(
            RagIndexVersion.workspace_id == wid, RagIndexVersion.request_key == key
        )
    )
    if existing:
        require(
            existing.dataset_version_id == vid
            and bool(existing.config.get("embedding")) == embedding,
            "IDEMPOTENCY_KEY_REUSED",
        )
        return existing
    profile = EmbeddingAdapter(settings or load_settings()).profile() if embedding else None
    row = RagIndexVersion(
        id=uid(),
        workspace_id=wid,
        dataset_version_id=vid,
        created_by=actor,
        request_key=key,
        content_sha256=v.content_sha256,
        config={
            "tokenizer": TOKENIZER,
            "fts": "postgresql-simple",
            "embedding": profile,
            "dimensions": profile["dimensions"] if profile else None,
            "vector_store": "postgresql-json-exact-cosine" if profile else None,
            "schema": "rag-index.v1",
        },
    )
    session.add(row)
    session.flush()
    enqueue(session, wid, row.id, "rag.index.build")
    return row


def build_index(session: Session, settings: Settings, row: RagIndexVersion) -> None:
    started = time.monotonic()
    member(session, row.workspace_id, row.created_by, True)
    v = version(session, row.workspace_id, row.dataset_version_id, "rag")
    require(v.content_sha256 == row.content_sha256, "MATERIALIZATION_HASH_MISMATCH")
    manifest, records = read_release(settings, v)
    manifest_samples = {item["sample_id"]: item for item in manifest["samples"]}
    require(0 < len(records) <= 5000, "RAG_SCOPE_TOO_LARGE")
    pending: list[RagChunk] = []
    for sample_id, record in records.items():
        sample = session.get(CandidateSample, sample_id)
        require(
            sample and sample.workspace_id == row.workspace_id and sample.build_id == v.build_id,
            "INVALID_SAMPLE_EVIDENCE",
        )
        assert sample is not None
        p = sample.payload
        require(
            digest(p) == sample.payload_hash == manifest_samples[sample_id]["payload_sha256"],
            "MATERIALIZATION_HASH_MISMATCH",
        )
        seg = session.get(Segment, str(p.get("segment_id")))
        require(
            seg
            and session.scalar(
                select(SampleEvidence.id).where(
                    SampleEvidence.candidate_sample_id == sample.id,
                    SampleEvidence.segment_id == p.get("segment_id"),
                )
            ),
            "INVALID_SAMPLE_EVIDENCE",
        )
        assert seg is not None
        require(seg.quality_state in {"reviewed", "approved"}, "QUALITY_GATE_FAILED")
        require(
            seg.document_version_id == p.get("document_version_id")
            and seg.source_id == p.get("source_id"),
            "INVALID_SAMPLE_EVIDENCE",
        )
        require(
            record.get("text") == p.get("text") and record.get("segment_id") == seg.id,
            "MATERIALIZATION_HASH_MISMATCH",
        )
        asset = source_asset(session, row.workspace_id, seg.id)
        require(permitted(session, row.workspace_id, asset.id, "rag"), "PURPOSE_GRANT_MISSING")
        require(
            not session.scalar(
                select(QualityIssue.id).where(
                    QualityIssue.workspace_id == row.workspace_id,
                    QualityIssue.asset_id == asset.id,
                    QualityIssue.status != "resolved",
                )
            ),
            "QUALITY_GATE_FAILED",
        )
        pending.append(
            RagChunk(
                index_version_id=row.id,
                sample_id=sample.id,
                segment_id=seg.id,
                asset_id=asset.id,
                text=str(record["text"]),
                content_sha256=hashlib.sha256(str(record["text"]).encode()).hexdigest(),
                provenance={
                    "source_id": seg.source_id,
                    "document_version_id": seg.document_version_id,
                    "asset_id": asset.id,
                    "location": seg.location_json,
                    "dataset_version_id": v.id,
                    "chunk_config": {key: p.get(key) for key in ("chunk_size", "overlap", "unit")},
                },
            )
        )
    profile = row.config.get("embedding")
    usage: dict[str, Any] = {}
    reused = 0
    if profile:
        # Only reuse immutable vectors from the same workspace/model/content. Current
        # grant and quality were checked above; reuse never bypasses those checks.
        prior = session.execute(
            select(RagChunk, RagIndexVersion)
            .join(RagIndexVersion)
            .where(
                RagIndexVersion.workspace_id == row.workspace_id,
                RagIndexVersion.status == "succeeded",
                RagChunk.embedding.is_not(None),
            )
        ).all()
        cache = {
            c.content_sha256: c.embedding for c, i in prior if i.config.get("embedding") == profile
        }
        missing = []
        for chunk in pending:
            if chunk.content_sha256 in cache:
                chunk.embedding = cache[chunk.content_sha256]
                reused += 1
            else:
                missing.append(chunk)
        if missing:
            vectors, usage = EmbeddingAdapter(settings).embed([c.text for c in missing], profile)
            for chunk, vector in zip(missing, vectors, strict=True):
                chunk.embedding = vector
    session.add_all(pending)
    row.config = {
        **row.config,
        "build_stats": {
            "elapsed_ms": (time.monotonic() - started) * 1000,
            "vectors_reused": reused,
            "vectors_encoded": len(pending) - reused if profile else 0,
            "vector_bytes_float32": len(pending) * profile["dimensions"] * 4 if profile else 0,
            "usage": usage,
        },
    }
    row.chunk_count = len(records)
    row.status = "succeeded"


def allowed_chunks(session: Session, wid: str, iid: str) -> tuple[RagIndexVersion, list[RagChunk]]:
    index = session.scalar(
        select(RagIndexVersion).where(
            RagIndexVersion.id == iid, RagIndexVersion.workspace_id == wid
        )
    )
    require(index, "NOT_FOUND")
    assert index is not None
    require(index.status == "succeeded", "RAG_INDEX_NOT_READY")
    version(session, wid, index.dataset_version_id, "rag")
    chunks = session.scalars(
        select(RagChunk)
        .join(Segment, Segment.id == RagChunk.segment_id)
        .where(
            RagChunk.index_version_id == iid,
            Segment.workspace_id == wid,
            Segment.quality_state.in_(["reviewed", "approved"]),
        )
    ).all()
    grants: dict[str, bool] = {}
    for chunk in chunks:
        if chunk.asset_id not in grants:
            blocked = session.scalar(
                select(QualityIssue.id).where(
                    QualityIssue.workspace_id == wid,
                    QualityIssue.asset_id == chunk.asset_id,
                    QualityIssue.status != "resolved",
                )
            )
            grants[chunk.asset_id] = permitted(session, wid, chunk.asset_id, "rag") and not blocked
    return index, [c for c in chunks if grants[c.asset_id]]


def retrieve(
    session: Session,
    wid: str,
    actor: str,
    iid: str,
    query: str,
    strategy: str = "bm25",
    top_k: int = 5,
    rerank: bool = False,
    min_similarity: float = 0.5,
    settings: Settings | None = None,
) -> RetrievalTrace:
    member(session, wid, actor)
    require(
        strategy in {"fts", "bm25", "hybrid", "vector", "semantic_hybrid"}, "ADAPTER_UNAVAILABLE"
    )
    started = time.monotonic()
    index, chunks = allowed_chunks(session, wid, iid)
    documents = {c.id: c.text for c in chunks}
    sparse = bm25(query, documents)
    fts: dict[str, float] = {}
    if strategy in {"fts", "hybrid"} and chunks:
        rows = session.execute(
            text("""SELECT id,
            ts_rank_cd(to_tsvector('simple', text), plainto_tsquery('simple', :query)) AS score
            FROM rag_chunks WHERE index_version_id=:iid
            AND to_tsvector('simple', text) @@ plainto_tsquery('simple', :query)"""),
            {"iid": iid, "query": query},
        )
        fts = {r.id: float(r.score) for r in rows if r.id in documents}

    def ordered(scores: dict[str, float]) -> list[str]:
        return sorted(scores, key=lambda k: (-scores[k], k))

    dense: dict[str, float] = {}
    embedding_usage: dict[str, Any] = {}
    if strategy in {"vector", "semantic_hybrid"}:
        require(index.config.get("embedding"), "ADAPTER_UNAVAILABLE")
        if chunks:
            vectors, embedding_usage = EmbeddingAdapter(settings or load_settings()).embed(
                [query], index.config["embedding"]
            )
            require(all(c.embedding is not None for c in chunks), "EMBEDDING_INDEX_INCOMPLETE")
            dense = {c.id: cosine(vectors[0], c.embedding or []) for c in chunks}
            dense = {key: score for key, score in dense.items() if score >= min_similarity}
    fused = reciprocal_rank([ordered(sparse), ordered(fts)]) if strategy == "hybrid" else {}
    if strategy == "semantic_hybrid":
        fused = reciprocal_rank([ordered(sparse), ordered(dense)])
    scores = (
        fts
        if strategy == "fts"
        else dense
        if strategy == "vector"
        else fused
        if strategy in {"hybrid", "semantic_hybrid"}
        else sparse
    )
    ranking = ordered(scores)
    original_ranks = {key: i + 1 for i, key in enumerate(ranking)}
    coverage = {
        key: len(set(tokens(query)) & set(tokens(documents[key]))) / max(1, len(set(tokens(query))))
        for key in ranking
    }
    if rerank:
        ranking.sort(key=lambda key: (-coverage[key], -scores[key], key))
    by_id = {c.id: c for c in chunks}
    hits = [
        {
            "chunk_id": key,
            "sample_id": by_id[key].sample_id,
            "segment_id": by_id[key].segment_id,
            **by_id[key].provenance,
            "text": by_id[key].text,
            "rank": i + 1,
            "original_rank": original_ranks[key],
            "scores": {
                "cosine": dense.get(key),
                "bm25": sparse.get(key),
                "fts": fts.get(key),
                "rrf": fused.get(key),
                "rerank_coverage": coverage[key] if rerank else None,
                "query_coverage": coverage[key],
            },
        }
        for i, key in enumerate(ranking[:top_k])
    ]
    trace = RetrievalTrace(
        id=uid(),
        workspace_id=wid,
        index_version_id=iid,
        created_by=actor,
        query=query,
        config={
            "strategy": strategy,
            "top_k": top_k,
            "min_similarity": min_similarity,
            "rrf_constant": 60,
            "embedding": index.config.get("embedding"),
            "reranker": "token-coverage-v1" if rerank else None,
        },
        result={
            "status": (
                "LOW_EVIDENCE"
                if hits
                and max(coverage[key] for key in ranking[:top_k]) < 0.5
                and not any(key in dense for key in ranking[:top_k])
                else "EVIDENCE_FOUND"
                if hits
                else "NO_EVIDENCE"
            ),
            "hits": hits,
            "generation": {"status": "NOT_CONFIGURED", "answer": None, "citations": []},
            "elapsed_ms": (time.monotonic() - started) * 1000,
            "dataset_version_id": index.dataset_version_id,
            "index_version_id": iid,
            "algorithm_version": "semantic-v1"
            if strategy in {"vector", "semantic_hybrid"}
            else "lexical-v1",
            "embedding_usage": embedding_usage,
            "score_semantics": "not probabilities",
        },
    )
    session.add(trace)
    session.flush()
    return trace


def visible_trace(session: Session, wid: str, trace: RetrievalTrace) -> dict[str, Any]:
    _, allowed = allowed_chunks(session, wid, trace.index_version_id)
    ids = {c.id for c in allowed}
    hits = [hit for hit in trace.result["hits"] if hit["chunk_id"] in ids]
    return {
        "trace_id": trace.id,
        "query": trace.query,
        "config": trace.config,
        **trace.result,
        "hits": hits,
        "status": (trace.result["status"] if hits else "NO_EVIDENCE"),
        "redacted_hit_count": len(trace.result["hits"]) - len(hits),
    }


def create_suite(
    session: Session,
    settings: Settings,
    wid: str,
    actor: str,
    vid: str,
    name: str,
    note: str,
    no_answer: list[str],
) -> RagEvaluationSuite:
    v = version(session, wid, vid, "evaluation")
    _, records = read_release(settings, v)
    cases = []
    for key, record in records.items():
        ids = list(record.get("evidence_ids", []))
        require(ids and record.get("reference_answer"), "INVALID_SAMPLE_EVIDENCE")
        for sid in ids:
            asset = source_asset(session, wid, sid)
            require(permitted(session, wid, asset.id, "evaluation"), "PURPOSE_GRANT_MISSING")
        cases.append(
            {
                "case_id": key,
                "query": record["question"],
                "reference_answer": record["reference_answer"],
                "relevance": {sid: 1 for sid in ids},
                "no_answer": False,
            }
        )
    for i, query in enumerate(no_answer):
        cases.append(
            {
                "case_id": f"no-answer-{i}",
                "query": query,
                "reference_answer": None,
                "relevance": {},
                "no_answer": True,
            }
        )
    require(0 < len(cases) <= 100, "RAG_SCOPE_TOO_LARGE")
    suite = RagEvaluationSuite(
        workspace_id=wid,
        dataset_version_id=vid,
        name=name,
        cases=cases,
        content_sha256=digest(cases),
        reviewed_by=actor,
        annotation_note=note,
    )
    session.add(suite)
    session.flush()
    return suite


def evaluate(session: Session, row: RagEvaluationRun) -> None:
    member(session, row.workspace_id, row.created_by, True)
    suite = session.get(RagEvaluationSuite, row.suite_id)
    require(suite and suite.workspace_id == row.workspace_id, "NOT_FOUND")
    assert suite is not None
    version(session, row.workspace_id, suite.dataset_version_id, "evaluation")
    require(digest(suite.cases) == suite.content_sha256, "MATERIALIZATION_HASH_MISMATCH")
    index, chunks = allowed_chunks(session, row.workspace_id, row.index_version_id)
    available = {c.segment_id for c in chunks}
    results = []
    for case in suite.cases:
        for sid in case["relevance"]:
            asset = source_asset(session, row.workspace_id, sid)
            require(
                permitted(session, row.workspace_id, asset.id, "evaluation"),
                "PURPOSE_GRANT_MISSING",
            )
        # Missing evidence is a measured retrieval failure, never remapped by filename.
        trace = retrieve(
            session,
            row.workspace_id,
            row.created_by,
            row.index_version_id,
            case["query"],
            **row.config,
        )
        equivalents: dict[str, str] = {}
        for old_id in case["relevance"]:
            old_seg = session.get(Segment, old_id)
            for edge in session.scalars(
                select(LineageEdge).where(
                    LineageEdge.workspace_id == row.workspace_id,
                    LineageEdge.from_type == "Segment",
                    LineageEdge.from_id == old_id,
                    LineageEdge.to_type == "Segment",
                    LineageEdge.relation == "reprocessed_equivalent",
                )
            ):
                new_seg = session.get(Segment, edge.to_id)
                if (
                    old_seg
                    and new_seg
                    and new_seg.content_hash == old_seg.content_hash
                    and (
                        source_asset(session, row.workspace_id, new_seg.id).id
                        == source_asset(session, row.workspace_id, old_id).id
                    )
                ):
                    equivalents[new_seg.id] = old_id
        measured = metrics(
            case["relevance"],
            [equivalents.get(h["segment_id"], h["segment_id"]) for h in trace.result["hits"]],
            row.config["top_k"],
        )
        results.append(
            {
                "case_id": case["case_id"],
                "trace_id": trace.id,
                "metrics": measured,
                "elapsed_ms": trace.result["elapsed_ms"],
                "evidence_equivalence": equivalents,
                "missing_index_evidence": sorted(
                    set(case["relevance"]) - available - set(equivalents.values())
                ),
            }
        )
    summary: dict[str, Any] = {}
    for key in ("recall", "precision", "mrr", "ndcg", "hit", "no_answer_correct"):
        values = [r["metrics"][key] for r in results if r["metrics"][key] is not None]
        summary[key] = {
            "value": sum(values) / len(values) if values else None,
            "denominator": len(values),
        }
    latencies = sorted(r["elapsed_ms"] for r in results)
    summary["latency_ms"] = {
        f"p{p}": latencies[math.ceil(len(latencies) * p / 100) - 1] for p in (50, 95)
    }
    row.report = {
        "metric_version": "segment-relevance-v1",
        "k": row.config["top_k"],
        "ndcg_labels": "binary relevance (grade=1)",
        "suite_id": suite.id,
        "suite_sha256": suite.content_sha256,
        "index_version_id": index.id,
        "dataset_version_id": index.dataset_version_id,
        "strategy": row.config,
        "index_config": index.config,
        "case_count": len(results),
        "cases": results,
        "metrics": summary,
        "model": None,
        "token_cost": None,
        "answer_quality": "NOT_EVALUATED",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    row.status = "succeeded"


def feedback_issue(session: Session, wid: str, sid: str, category: str, note: str) -> QualityIssue:
    asset = source_asset(session, wid, sid)
    seg = session.get(Segment, sid)
    assert seg is not None
    dv = session.get(DocumentVersion, seg.document_version_id)
    assert dv is not None
    run = None
    if dv.run_id:
        run = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.id == dv.run_id, PipelineRun.workspace_id == wid)
            .with_for_update()
        )
        require(
            run and run.status in {"succeeded", "awaiting_review", "failed"},
            "INVALID_STATE_TRANSITION",
        )
    issue = QualityIssue(
        id=uid(),
        workspace_id=wid,
        asset_id=asset.id,
        run_id=dv.run_id,
        reason=f"RAG/{category}: {note}",
        severity="warning",
    )
    session.add(issue)
    if run:
        run.status = "awaiting_review"
    session.flush()
    return issue
