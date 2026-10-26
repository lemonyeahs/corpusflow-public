"""Deterministic, bounded quality evaluations over fixed dataset inputs.

Authorization is always a separate hard gate. No aggregate quality score is used.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from corpusflow.adapters.storage import S3ObjectStore
from corpusflow.core.config import Settings
from corpusflow.db.models import (
    Asset,
    BuildInput,
    CandidateSample,
    Dataset,
    DatasetBuild,
    DatasetQualityReport,
    DatasetVersion,
    DatasetVersionComparison,
    DatasetVersionSample,
    Document,
    DocumentVersion,
    LicenseEvidence,
    LicenseGrant,
    NodeRun,
    QualityEvaluationRun,
    QualityIssue,
    QualityMetricResult,
    QualityRuleSet,
    QualityRuleVersion,
    SampleEvidence,
    SampleReview,
    Segment,
)
from corpusflow.services.dataset_materializer import (
    TOKENIZER_VERSION,
    MaterializationError,
    _payload_evidence_ids,
    _split_for_source,
    _validate_product_payload,
)

# (method, direction, default threshold). None means descriptive, never a pass claim.
METRICS: dict[str, tuple[str, str, float | None]] = {
    "schema.validity": ("product schema valid samples / all samples", "higher", 1.0),
    "evidence.completeness": (
        "samples with exact persisted evidence and source chain / samples",
        "higher",
        1.0,
    ),
    "review.approval_rate": (
        "currently approved samples with latest approving review / samples",
        "higher",
        1.0,
    ),
    "sample.non_empty_rate": ("non-whitespace content samples / samples", "higher", 1.0),
    "sample.duplicate_rate": (
        "normalized duplicate content occurrences beyond first / samples",
        "lower",
        None,
    ),
    "sample.token_count": ("sum whitespace-token counts over product content", "descriptive", None),
    "segment.empty_rate": ("empty evidence segments / evidence segments", "lower", 0.0),
    "segment.duplicate_rate": (
        "normalized duplicates beyond first / evidence segments",
        "lower",
        None,
    ),
    "segment.abnormal_length_rate": (
        "segments outside 1..100000 characters / segments",
        "lower",
        None,
    ),
    "segment.location_coverage": (
        "segments with nonempty parser location / segments",
        "higher",
        None,
    ),
    "segment.source_completeness": (
        "segments with valid document/asset/source chain / segments",
        "higher",
        1.0,
    ),
    "document.metadata_completeness": (
        "present domain, year, document_type fields / 3 per asset",
        "higher",
        None,
    ),
    "document.abnormal_character_rate": (
        "replacement or non-whitespace control characters / extracted characters",
        "lower",
        None,
    ),
    "document.html_noise_rate": (
        "characters in residual HTML tags / extracted characters",
        "lower",
        None,
    ),
    "document.parsable_rate": (
        "successful input DocumentVersions / input DocumentVersions",
        "higher",
        None,
    ),
    "document.heading_coverage": (
        "segments with section_title / input segments; not structural accuracy",
        "higher",
        None,
    ),
    "evaluation.leakage_rate": (
        ("evaluation samples sharing source or exact evidence with published training / samples"),
        "lower",
        0.0,
    ),
    "rag.location_coverage": (
        "chunks with exact source/version/location references / chunks",
        "higher",
        1.0,
    ),
    "rag.original_coverage": (
        "unique source token positions covered by exported chunks / source tokens",
        "higher",
        None,
    ),
    "dpo.preference_resolution_rate": (
        "approved preference pairs / DPO preference candidates",
        "higher",
        1.0,
    ),
    "dpo.response_difference_rate": (
        "pairs with distinct chosen and rejected responses / DPO samples",
        "higher",
        1.0,
    ),
    "dpo.evidence_coverage": (
        "DPO samples with persisted evidence / DPO samples",
        "higher",
        1.0,
    ),
}
UNASSESSED = {
    "document.text_completeness": "no human reference transcription",
    "document.structure_accuracy": "no annotated section hierarchy",
    "document.formula_retention": "no reference formula inventory; markers are not accuracy",
    "document.table_retention": "no reference table structure",
    "document.ocr_noise": "no OCR ground truth; character heuristics reported separately",
    "segment.domain_relevance": "no reviewed domain labels or validated classifier",
    "domain.knowledge_coverage": "no trusted target domain catalogue or expected corpus",
}
MAX_SAMPLES = 5000


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def lock(session: Session, key: str) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int(hashlib.sha256(key.encode()).hexdigest()[:15], 16)},
        )


def default_rule_set(
    session: Session, workspace_id: str, actor_id: str
) -> tuple[QualityRuleSet, QualityRuleVersion]:
    lock(session, f"quality-rules:{workspace_id}")
    row = session.scalar(
        select(QualityRuleSet).where(
            QualityRuleSet.workspace_id == workspace_id, QualityRuleSet.name == "default"
        )
    )
    if row is None:
        row = QualityRuleSet(
            workspace_id=workspace_id,
            name="default",
            description="Deterministic quality rules; authorization is not configurable",
            product_type="*",
        )
        session.add(row)
        session.flush()
    version = session.scalar(
        select(QualityRuleVersion)
        .where(QualityRuleVersion.rule_set_id == row.id)
        .order_by(QualityRuleVersion.created_at.desc(), QualityRuleVersion.id.desc())
    )
    if version is None:
        config = {
            key: {"enabled": True, "threshold": definition[2], "manual_review": False}
            for key, definition in METRICS.items()
        }
        version = QualityRuleVersion(
            rule_set_id=row.id,
            version="1.0.0",
            rules_json=config,
            config_hash=digest(config),
            created_by=actor_id,
        )
        session.add(version)
        session.flush()
    return row, version


def scope_target(
    session: Session, wid: str, typ: str, target_id: str
) -> tuple[DatasetBuild, Dataset, DatasetVersion | None]:
    version = None
    if typ == "dataset_version":
        version = session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.workspace_id == wid,
                DatasetVersion.id == target_id,
                DatasetVersion.status == "published",
            )
        )
        if version is None:
            raise ValueError("NOT_FOUND")
        target_id = version.build_id
    elif typ != "dataset_build":
        raise ValueError("INVALID_ARGUMENT")
    build = session.scalar(
        select(DatasetBuild).where(DatasetBuild.workspace_id == wid, DatasetBuild.id == target_id)
    )
    dataset = session.get(Dataset, build.dataset_id) if build else None
    if build is None or dataset is None or dataset.workspace_id != wid:
        raise ValueError("NOT_FOUND")
    return build, dataset, version


def sample_text(product: str, payload: dict[str, Any]) -> str:
    if product == "sft":
        return "\n".join(
            str(x.get("content", "")) for x in payload.get("messages", []) if isinstance(x, dict)
        )
    if product == "evaluation":
        return str(payload.get("question", "")) + "\n" + str(payload.get("reference_answer", ""))
    if product == "dpo":
        return "\n".join(str(payload.get(key, "")) for key in ("prompt", "chosen", "rejected"))
    return str(payload.get("text", ""))


def normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def candidate_rows(
    session: Session, build: DatasetBuild, version: DatasetVersion | None
) -> list[CandidateSample]:
    query = select(CandidateSample).where(
        CandidateSample.workspace_id == build.workspace_id, CandidateSample.build_id == build.id
    )
    if version:
        query = query.join(
            DatasetVersionSample, DatasetVersionSample.candidate_sample_id == CandidateSample.id
        ).where(DatasetVersionSample.dataset_version_id == version.id)
    rows = list(session.scalars(query.order_by(CandidateSample.sample_key).limit(MAX_SAMPLES + 1)))
    if len(rows) > MAX_SAMPLES:
        raise ValueError("QUALITY_SCOPE_TOO_LARGE")
    return rows


def asset_for_segment(session: Session, wid: str, seg: Segment) -> Asset | None:
    return session.scalar(
        select(Asset)
        .join(Document, Document.asset_id == Asset.id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            DocumentVersion.id == seg.document_version_id,
            DocumentVersion.workspace_id == wid,
            Document.workspace_id == wid,
            Asset.workspace_id == wid,
            Asset.source_id == seg.source_id,
        )
    )


def allowed(session: Session, wid: str, asset: Asset, purpose: str) -> bool:
    grant = session.scalar(
        select(LicenseGrant)
        .where(
            LicenseGrant.workspace_id == wid,
            LicenseGrant.asset_id == asset.id,
            LicenseGrant.purpose == purpose,
        )
        .order_by(LicenseGrant.created_at.desc(), LicenseGrant.id.desc())
    )
    if grant is None or grant.status != "confirmed" or not grant.evidence_id:
        return False
    evidence = session.get(LicenseEvidence, grant.evidence_id)
    return bool(
        evidence
        and evidence.workspace_id == wid
        and evidence.asset_id == asset.id
        and evidence.uri
        and evidence.legal_basis
    )


def distribution(values: list[str], weights: list[int] | None = None) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for index, value in enumerate(values):
        counts[value] += weights[index] if weights is not None else 1
    total = sum(counts.values())
    return {
        "counts": dict(sorted(counts.items())),
        "denominator": total,
        "ratios": {key: value / total if total else None for key, value in sorted(counts.items())},
    }


def labels(asset: Asset) -> list[str]:
    metadata = asset.metadata_json or {}
    raw = metadata.get("domains") or metadata.get("domain") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(x) for x in raw] if isinstance(raw, list) else []


def composition(
    session: Session,
    build: DatasetBuild,
    dataset: Dataset,
    version: DatasetVersion | None,
    samples: list[CandidateSample],
) -> dict[str, Any]:
    fields: dict[str, list[str]] = {
        key: [] for key in ("source", "domain", "document_type", "year", "split")
    }
    tokens = []
    for sample in samples:
        payload = sample.payload
        seg_id = next(iter(_payload_evidence_ids(dataset.product_type, payload)), "")
        seg = session.get(Segment, seg_id)
        asset = asset_for_segment(session, build.workspace_id, seg) if seg else None
        metadata = asset.metadata_json if asset else {}
        fields["source"].append(sample.source_id)
        fields["domain"].append(
            "|".join(sorted(set(labels(asset)))) if asset and labels(asset) else "unknown"
        )
        fields["document_type"].append(str(metadata.get("document_type", "unknown")))
        fields["year"].append(str(metadata.get("year", "unknown")))
        split = (
            _split_for_source(sample.source_id)
            if dataset.product_type in {"sft", "pretrain", "dpo"}
            else "all"
        )
        if version:
            split = (
                session.scalar(
                    select(DatasetVersionSample.split).where(
                        DatasetVersionSample.dataset_version_id == version.id,
                        DatasetVersionSample.candidate_sample_id == sample.id,
                    )
                )
                or "unknown"
            )
        fields["split"].append(split)
        tokens.append(len(sample_text(dataset.product_type, payload).split()))
    result: dict[str, Any] = {
        key: {"samples": distribution(values), "tokens": distribution(values, tokens)}
        for key, values in fields.items()
    }
    targets = build.config_json.get("target_ratios", {})
    deviations = {}
    for field, targets_by_label in targets.items() if isinstance(targets, dict) else []:
        if field not in result or not isinstance(targets_by_label, dict):
            continue
        actual = result[field]["samples"]["ratios"]
        deviations[field] = {
            key: {
                "target": target,
                "actual": actual.get(key, 0),
                "delta": actual.get(key, 0) - target,
            }
            for key, target in targets_by_label.items()
            if isinstance(target, (int, float)) and 0 <= target <= 1
        }
    groups: defaultdict[str, set[str]] = defaultdict(set)
    for source, split in zip(fields["source"], fields["split"], strict=True):
        groups[source].add(split)
    result.update(
        {
            "sample_count": len(samples),
            "token_count": sum(tokens),
            "tokenizer_version": version.tokenizer_version if version else TOKENIZER_VERSION,
            "target_deviations": deviations,
            "target_status": "CONFIGURED" if deviations else "NOT_CONFIGURED",
            "source_split_leaks": [key for key, value in groups.items() if len(value) > 1],
            "source_concentration": max(
                result["source"]["samples"]["ratios"].values(), default=None
            ),
            "domain_unit": "exclusive domain combination per sample; multi-label coverage separate",
            "scope": "fixed dataset input samples",
        }
    )
    return result


def evaluate(
    session: Session,
    workspace_id: str,
    actor_id: str,
    target_type: str,
    target_id: str,
    rule_version_id: str | None = None,
    idempotency_key: str | None = None,
    settings: Settings | None = None,
) -> tuple[QualityEvaluationRun, dict[str, Any]]:
    build, dataset, version = scope_target(session, workspace_id, target_type, target_id)
    rule_set, rule_version = default_rule_set(session, workspace_id, actor_id)
    if rule_version_id:
        selected = session.scalar(
            select(QualityRuleVersion)
            .join(QualityRuleSet, QualityRuleSet.id == QualityRuleVersion.rule_set_id)
            .where(
                QualityRuleVersion.id == rule_version_id,
                QualityRuleSet.workspace_id == workspace_id,
            )
        )
        if selected is None:
            raise ValueError("NOT_FOUND")
        rule_version = selected
        rule_set = session.get(QualityRuleSet, selected.rule_set_id) or rule_set
    if idempotency_key:
        lock(session, f"quality-evaluate:{workspace_id}:{idempotency_key}")
        for prior in session.scalars(
            select(QualityEvaluationRun).where(QualityEvaluationRun.workspace_id == workspace_id)
        ):
            if prior.config_snapshot.get("idempotency_key") == idempotency_key:
                if (prior.target_type, prior.target_id, prior.rule_version_id) != (
                    target_type,
                    target_id,
                    rule_version.id,
                ):
                    raise ValueError("IDEMPOTENCY_KEY_REUSED")
                return prior, prior.config_snapshot["report"]
    release = read_release(settings, version) if settings and version else None
    samples = candidate_rows(session, build, version)
    product = dataset.product_type
    purpose = {
        "sft": "training",
        "pretrain": "training",
        "rag": "rag",
        "evaluation": "evaluation",
        "dpo": "training",
    }[product]
    run = QualityEvaluationRun(
        workspace_id=workspace_id,
        rule_set_id=rule_set.id,
        rule_version_id=rule_version.id,
        target_type=target_type,
        target_id=target_id,
        product_type=product,
        created_by=actor_id,
        started_at=datetime.now(UTC),
        status="running",
    )
    session.add(run)
    session.flush()
    assert run.started_at is not None
    computed_at = run.started_at.isoformat()
    metrics: list[dict[str, Any]] = []

    def metric(
        key: str, numerator: float, denominator: float, evidence: Any = None, unit: str = "ratio"
    ) -> None:
        method, direction, default = METRICS[key]
        rule = rule_version.rules_json.get(key, {"enabled": True, "threshold": default})
        threshold = rule.get("threshold", default)
        value = numerator / denominator if denominator else None
        status = "NOT_EVALUATED" if value is None or not rule.get("enabled", True) else "MEASURED"
        if status == "MEASURED" and threshold is not None:
            status = (
                "PASS"
                if (value >= threshold if direction == "higher" else value <= threshold)
                else "FAIL"
            )
        metrics.append(
            {
                "metric_id": key,
                "metric_version": "1.0",
                "method": method,
                "category": key.split(".")[0],
                "value": value,
                "numerator": numerator,
                "denominator": denominator,
                "unit": unit,
                "direction": direction,
                "threshold": threshold,
                "status": status,
                "sample_count": int(denominator),
                "rule_version_id": rule_version.id,
                "computed_at": computed_at,
                "scope": {"target_type": target_type, "target_id": target_id},
                "evidence": evidence or {},
            }
        )

    segments: dict[str, Segment] = {}
    assets: dict[str, Asset] = {}
    sample_segments: dict[str, list[Segment]] = {}
    schema_valid = evidence_valid = reviewed = authorized = location_valid = 0
    review_records = []
    for sample in samples:
        payload = sample.payload
        try:
            _validate_product_payload(product, payload)
            schema_valid += 1
        except (MaterializationError, TypeError, KeyError):
            pass
        ids = _payload_evidence_ids(product, payload)
        stored_ids = set(
            session.scalars(
                select(SampleEvidence.segment_id).where(
                    SampleEvidence.candidate_sample_id == sample.id
                )
            )
        )
        chain = []
        for sid in ids:
            seg = session.scalar(
                select(Segment).where(Segment.id == sid, Segment.workspace_id == workspace_id)
            )
            if seg:
                segments[seg.id] = seg
                chain.append(seg)
        sample_segments[sample.id] = chain
        sample_assets = [asset_for_segment(session, workspace_id, seg) for seg in chain]
        for asset in sample_assets:
            if asset:
                assets[asset.id] = asset
        complete = (
            bool(ids)
            and len(chain) == len(ids)
            and set(ids) == stored_ids
            and all(sample_assets)
            and all(seg.source_id == sample.source_id for seg in chain)
        )
        evidence_valid += int(complete)
        authorized += int(
            complete
            and all(
                allowed(session, workspace_id, asset, purpose) for asset in sample_assets if asset
            )
        )
        latest_review = session.scalar(
            select(SampleReview)
            .where(SampleReview.candidate_sample_id == sample.id)
            .order_by(SampleReview.created_at.desc(), SampleReview.id.desc())
        )
        reviewed += int(
            sample.status == "approved"
            and latest_review is not None
            and latest_review.decision == "approved"
        )
        if latest_review:
            review_records.append(
                {
                    "sample_id": sample.id,
                    "review_id": latest_review.id,
                    "reviewer_id": latest_review.reviewer_id,
                    "decision": latest_review.decision,
                }
            )
        if product == "rag" and chain:
            seg = chain[0]
            location_valid += int(
                bool(seg.location_json)
                and payload.get("location") == seg.location_json
                and payload.get("document_version_id") == seg.document_version_id
                and payload.get("source_id") == seg.source_id
            )
    size = len(samples)
    texts = [sample_text(product, sample.payload) for sample in samples]
    metric("schema.validity", schema_valid, size)
    metric(
        "evidence.completeness",
        evidence_valid,
        size,
        {
            "sample_segments": {
                key: [seg.id for seg in value] for key, value in sample_segments.items()
            }
        },
    )
    metric("review.approval_rate", reviewed, size, review_records)
    metric("sample.non_empty_rate", sum(bool(value.strip()) for value in texts), size)
    metric("sample.duplicate_rate", size - len({normalized(value) for value in texts}), size)
    metric(
        "sample.token_count",
        sum(len(value.split()) for value in texts),
        1,
        {"tokenizer_version": TOKENIZER_VERSION},
        "tokens",
    )
    segs = list(segments.values())
    count = len(segs)
    metric("segment.empty_rate", sum(not seg.text.strip() for seg in segs), count)
    metric("segment.duplicate_rate", count - len({normalized(seg.text) for seg in segs}), count)
    metric(
        "segment.abnormal_length_rate", sum(not 1 <= len(seg.text) <= 100000 for seg in segs), count
    )
    metric("segment.location_coverage", sum(bool(seg.location_json) for seg in segs), count)
    metric(
        "segment.source_completeness",
        sum(asset_for_segment(session, workspace_id, seg) is not None for seg in segs),
        count,
    )
    metric(
        "document.metadata_completeness",
        sum(
            bool(labels(asset))
            + bool(asset.metadata_json.get("year"))
            + bool(asset.metadata_json.get("document_type"))
            for asset in assets.values()
        ),
        3 * len(assets),
    )
    content = "\n".join(seg.text for seg in segs)
    metric(
        "document.abnormal_character_rate",
        sum(char == "\ufffd" or (ord(char) < 32 and char not in "\n\t\r") for char in content),
        len(content),
    )
    metric(
        "document.html_noise_rate",
        sum(len(match) for match in re.findall(r"</?[a-zA-Z][^>]*>", content)),
        len(content),
    )
    docs = [
        session.get(DocumentVersion, did)
        for did in sorted({seg.document_version_id for seg in segs})
    ]
    metric(
        "document.parsable_rate",
        sum(doc is not None and doc.status == "succeeded" for doc in docs),
        len(docs),
    )
    metric("document.heading_coverage", sum(bool(seg.section_title) for seg in segs), count)
    if product == "rag":
        metric("rag.location_coverage", location_valid, size)
        positions: defaultdict[str, set[int]] = defaultdict(set)
        for sample in samples:
            for seg in sample_segments[sample.id]:
                source_tokens = seg.text.split()
                chunk_tokens = str(sample.payload.get("text", "")).split()
                for start in range(len(source_tokens) - len(chunk_tokens) + 1):
                    if (
                        chunk_tokens
                        and source_tokens[start : start + len(chunk_tokens)] == chunk_tokens
                    ):
                        positions[seg.id].update(range(start, start + len(chunk_tokens)))
        metric(
            "rag.original_coverage",
            sum(len(value) for value in positions.values()),
            sum(len(seg.text.split()) for seg in segs),
            {"unit": "unique source token positions; exact contiguous token matches"},
        )
    leakage = []
    if product == "evaluation":
        training_samples = list(
            session.scalars(
                select(CandidateSample)
                .join(
                    DatasetVersionSample,
                    DatasetVersionSample.candidate_sample_id == CandidateSample.id,
                )
                .join(DatasetVersion, DatasetVersion.id == DatasetVersionSample.dataset_version_id)
                .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
                .where(
                    DatasetVersion.workspace_id == workspace_id,
                    Dataset.product_type.in_(["sft", "pretrain"]),
                    DatasetVersion.status == "published",
                )
            )
        )
        training_sources = {s.source_id for s in training_samples}
        training_texts: set[str] = set()
        for sample in training_samples:
            for sid in _payload_evidence_ids("pretrain", sample.payload):
                seg = session.get(Segment, sid)
                if seg and seg.workspace_id == workspace_id:
                    training_texts.add(normalized(seg.text))
        leakage = [
            sample.id
            for sample in samples
            if sample.source_id in training_sources
            or any(normalized(seg.text) in training_texts for seg in sample_segments[sample.id])
        ]
        metric(
            "evaluation.leakage_rate",
            len(leakage),
            size,
            {
                "sample_ids": leakage,
                "method": "source OR exact evidence; semantic near-duplicates NOT_EVALUATED",
            },
        )
    if product == "dpo":
        resolved = sum(
            bool(sample.payload.get("chosen")) and bool(sample.payload.get("rejected"))
            for sample in samples
        )
        distinct = sum(
            sample.payload.get("chosen") != sample.payload.get("rejected") for sample in samples
        )
        metric("dpo.preference_resolution_rate", resolved, size)
        metric("dpo.response_difference_rate", distinct, size)
        metric("dpo.evidence_coverage", evidence_valid, size)
    for key, reason in UNASSESSED.items():
        metrics.append(
            {
                "metric_id": key,
                "metric_version": "1.0",
                "method": reason,
                "category": key.split(".")[0],
                "value": None,
                "numerator": None,
                "denominator": None,
                "unit": "ratio",
                "direction": "higher",
                "threshold": None,
                "status": "NOT_EVALUATED",
                "sample_count": size,
                "rule_version_id": rule_version.id,
                "computed_at": computed_at,
                "scope": {"target_type": target_type, "target_id": target_id},
                "evidence": {"reason": reason},
            }
        )
    input_rows = list(session.scalars(select(BuildInput).where(BuildInput.build_id == build.id)))
    snapshot_ok = (
        digest(build.config_json) == build.config_hash
        and all(digest(sample.payload) == sample.payload_hash for sample in samples)
        and all(
            row.segment_id in segments
            and segments[row.segment_id].content_hash == row.content_sha256
            for row in input_rows
        )
    )
    source_issues = list(
        session.scalars(
            select(QualityIssue).where(
                QualityIssue.workspace_id == workspace_id,
                QualityIssue.asset_id.in_(list(assets)),
                QualityIssue.status != "resolved",
            )
        )
    )
    stats = composition(session, build, dataset, version, samples)
    failures = [m["metric_id"] for m in metrics if m["status"] == "FAIL"]
    # These are unconditional gates and cannot be disabled or compensated by a score.
    gates = {
        "published_content": release is None
        or all(
            sample.id in release[1]
            and sample_text(product, sample.payload) == sample_text(product, release[1][sample.id])
            for sample in samples
        ),
        "authorization": bool(size) and authorized == size,
        "evidence": bool(size) and evidence_valid == size,
        "schema": bool(size) and schema_valid == size,
        "review": bool(size) and reviewed == size,
        "snapshot": snapshot_ok,
        "source_quality": not source_issues
        and all(seg.quality_state == "reviewed" for seg in segs),
        "split_leakage": not stats["source_split_leaks"],
        "evaluation_leakage": not leakage,
    }
    report: dict[str, Any] = {
        "report_version": "p1c.v2",
        "evaluation_id": run.id,
        "target_type": target_type,
        "target_id": target_id,
        "dataset_id": dataset.id,
        "dataset_version_id": version.id if version else None,
        "build_id": build.id,
        "product_type": product,
        "purpose": purpose,
        "rules": rule_version.rules_json,
        "rule_version": rule_version.version,
        "rule_version_id": rule_version.id,
        "rule_config_hash": rule_version.config_hash,
        "input_hash": digest(
            {
                "config": build.config_hash,
                "samples": [
                    (sample.id, digest(sample.payload), sample.status) for sample in samples
                ],
            }
        ),
        "build_config_hash": build.config_hash,
        "sample_count": size,
        "tokenizer_version": version.tokenizer_version if version else TOKENIZER_VERSION,
        "metrics": metrics,
        "gates": gates,
        "authorization_gate": "PASS" if gates["authorization"] else "FAIL",
        "quality_status": "PASS" if not failures and all(gates.values()) else "FAIL",
        "failed_metrics": failures,
        "unassessed": [m["metric_id"] for m in metrics if m["status"] == "NOT_EVALUATED"],
        "composition": stats,
        "reviews": review_records,
        "source_quality_issues": [issue.id for issue in source_issues],
        "inputs": [
            {
                "segment_id": seg.id,
                "document_version_id": seg.document_version_id,
                "source_id": seg.source_id,
                "content_hash": seg.content_hash,
                "location": seg.location_json,
            }
            for seg in segs
        ],
        "asset_ids": sorted(assets),
        "excluded": build.config_json.get("excluded", []),
        "lengths": {
            "samples_chars": [len(value) for value in texts],
            "segments_chars": [len(seg.text) for seg in segs],
        },
        "product_distributions": {
            key: dict(Counter(str(sample.payload.get(key, "unknown")) for sample in samples))
            for key in (
                ["question_type", "difficulty", "domain"]
                if product == "evaluation"
                else ["overlap", "unit"]
                if product == "rag"
                else ["preference_reason", "annotation_version"]
                if product == "dpo"
                else []
            )
        },
        "manifest": {"sha256": version.manifest_sha256, "content_sha256": version.content_sha256}
        if version
        else None,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    changes = []
    for doc in docs:
        if doc and doc.run_id:
            for node in session.scalars(select(NodeRun).where(NodeRun.run_id == doc.run_id)):
                changes.append(
                    {
                        "run_id": doc.run_id,
                        "node_run_id": node.id,
                        "operator": node.operator_key,
                        "input_count": node.input_count,
                        "output_count": node.output_count,
                        "filtered_count": node.filtered_count,
                        "duration_ms": node.duration_ms,
                        "failure": node.failure_code,
                    }
                )
    report["processing_records"] = changes
    for m in metrics:
        session.add(
            QualityMetricResult(
                evaluation_run_id=run.id,
                metric_id=m["metric_id"],
                metric_version=m["metric_version"],
                category=m["category"],
                value_numeric=m["value"],
                numerator=m["numerator"],
                denominator=m["denominator"],
                unit=m["unit"],
                direction=m["direction"],
                threshold_json={"value": m["threshold"]},
                status=m["status"],
                scope_json=m["scope"],
                evidence_json={"method": m["method"], "references": m["evidence"]},
            )
        )
    for failed in failures:
        session.add(
            QualityIssue(
                workspace_id=workspace_id,
                run_id=run.id,
                reason=f"quality evaluation {run.id}: {failed}",
                rule_version=rule_version.version,
                severity="high",
            )
        )
    run.metric_count = len(metrics)
    run.issue_count = len(failures)
    run.status = "succeeded"  # Computation succeeded; quality_status is independent.
    run.completed_at = datetime.now(UTC)
    run.config_snapshot = {
        "rules": rule_version.rules_json,
        "rule_config_hash": rule_version.config_hash,
        "idempotency_key": idempotency_key,
        "report": report,
    }
    if version:
        session.add(
            DatasetQualityReport(
                workspace_id=workspace_id,
                dataset_version_id=version.id,
                evaluation_run_id=run.id,
                report_json=report,
                report_sha256=digest(report),
            )
        )
    session.flush()
    return run, report


def coverage(
    session: Session,
    workspace_id: str,
    dataset_version_id: str | None = None,
    source_id: str | None = None,
    product_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    query = select(Asset).where(Asset.workspace_id == workspace_id)
    if source_id:
        query = query.where(Asset.source_id == source_id)
    if since:
        query = query.where(Asset.created_at >= since)
    if until:
        query = query.where(Asset.created_at <= until)
    selected: set[str] | None = None
    if dataset_version_id or product_type:
        versions = (
            select(DatasetVersion)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(DatasetVersion.workspace_id == workspace_id)
        )
        if dataset_version_id:
            scope_target(session, workspace_id, "dataset_version", dataset_version_id)
            versions = versions.where(DatasetVersion.id == dataset_version_id)
        if product_type:
            versions = versions.where(Dataset.product_type == product_type)
        selected = set()
        for version in session.scalars(versions):
            build, _, _ = scope_target(session, workspace_id, "dataset_version", version.id)
            for sample in candidate_rows(session, build, version):
                for sid in _payload_evidence_ids(product_type or "sft", sample.payload):
                    seg = session.get(Segment, sid)
                    asset = asset_for_segment(session, workspace_id, seg) if seg else None
                    if asset:
                        selected.add(asset.id)
    assets = [asset for asset in session.scalars(query) if selected is None or asset.id in selected]
    occurrences: Counter[str] = Counter()
    unique: defaultdict[str, set[str]] = defaultdict(set)
    for asset in assets:
        for label in labels(asset):
            occurrences[label] += 1
            unique[label].add(asset.id)
    fields = {
        "format": [asset.format for asset in assets],
        "source": [asset.source_id for asset in assets],
        "year": [str(asset.metadata_json.get("year", "unknown")) for asset in assets],
        "document_type": [
            str(asset.metadata_json.get("document_type", "unknown")) for asset in assets
        ],
        "quality": [asset.quality_status for asset in assets],
    }
    auth = {
        purpose: distribution(
            [
                "confirmed" if allowed(session, workspace_id, asset, purpose) else "denied"
                for asset in assets
            ]
        )
        for purpose in ["research", "training", "rag", "evaluation", "redistribute"]
    }
    levels: defaultdict[str, set[str]] = defaultdict(set)
    for label, ids in unique.items():
        levels[label.split("/")[0]].update(ids)
    return {
        "scope": "registered_assets",
        "as_of": datetime.now(UTC).isoformat(),
        "metric_definition_version": "p1c.v2",
        "asset_count": len(assets),
        "domain_label_occurrences": dict(occurrences),
        "domain_unique_assets": {key: len(ids) for key, ids in unique.items()},
        "domain_level1_unique_assets": {key: len(ids) for key, ids in levels.items()},
        "domain_level2_unique_assets": {key: len(ids) for key, ids in unique.items() if "/" in key},
        "format_distribution": dict(Counter(fields["format"])),
        "year_distribution": dict(Counter(fields["year"])),
        "distributions": {key: distribution(values) for key, values in fields.items()},
        "authorization": auth,
        "denominator": "filtered unique Asset IDs; domain labels are multi-label",
        "knowledge_coverage": "NOT_EVALUATED",
        "filters": {
            "source_id": source_id,
            "product_type": product_type,
            "dataset_version_id": dataset_version_id,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
    }


def ratios(session: Session, workspace_id: str, dataset_version_id: str) -> dict[str, Any]:
    build, dataset, version = scope_target(
        session, workspace_id, "dataset_version", dataset_version_id
    )
    return composition(session, build, dataset, version, candidate_rows(session, build, version))


def stable_samples(
    session: Session, build: DatasetBuild, dataset: Dataset, version: DatasetVersion
) -> list[dict[str, Any]]:
    result = []
    for sample in candidate_rows(session, build, version):
        anchors = []
        for sid in _payload_evidence_ids(dataset.product_type, sample.payload):
            seg = session.get(Segment, sid)
            asset = asset_for_segment(session, build.workspace_id, seg) if seg else None
            if seg and asset:
                anchors.append({"asset_id": asset.id, "location": seg.location_json})
        # Builder keys remain a useful tie-breaker, but immutable origins are the primary key.
        identity = digest(
            {
                "source": sample.source_id,
                "anchors": [] if dataset.product_type == "pretrain" else anchors,
                "type": dataset.product_type,
                "chunk_index": sample.payload.get("chunk_index"),
                "question": normalized(str(sample.payload.get("question", "")))
                if dataset.product_type == "evaluation"
                else None,
            }
        )
        result.append(
            {
                "sample_id": sample.id,
                "sample_key": sample.sample_key,
                "identity": identity,
                "source_id": sample.source_id,
                "content_hash": digest(sample_text(dataset.product_type, sample.payload)),
                "payload_hash": digest(sample.payload),
            }
        )
    return result


def diff_samples(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    remaining = list(right)
    kept: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for old in left:
        match = next(
            (
                row
                for row in remaining
                if row["identity"] == old["identity"] and row["content_hash"] == old["content_hash"]
            ),
            None,
        )
        if match is None:
            match = next((row for row in remaining if row["identity"] == old["identity"]), None)
        if match is None:
            removed.append(old)
        else:
            remaining.remove(match)
            (kept if old["content_hash"] == match["content_hash"] else changed).append(
                {"left": old, "right": match}
            )
    return {
        "added": remaining,
        "removed": removed,
        "retained": kept,
        "changed": changed,
        "counts": {
            "added": len(remaining),
            "removed": len(removed),
            "retained": len(kept),
            "changed": len(changed),
        },
    }


def read_release(
    settings: Settings, version: DatasetVersion
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if version.content_bytes > 50 * 1024 * 1024:
        raise ValueError("QUALITY_SCOPE_TOO_LARGE")
    store = S3ObjectStore(
        settings.object_store_endpoint,
        settings.object_store_bucket,
        settings.object_store_access_key.get_secret_value(),
        settings.object_store_secret_key.get_secret_value(),
    )
    try:
        manifest_data = store.get(version.manifest_storage_key)
        data = store.get(version.content_storage_key)
    except Exception as exc:
        raise ValueError("ADAPTER_UNAVAILABLE") from exc
    if (
        hashlib.sha256(manifest_data).hexdigest() != version.manifest_sha256
        or hashlib.sha256(data).hexdigest() != version.content_sha256
    ):
        raise ValueError("MATERIALIZATION_HASH_MISMATCH")
    manifest = json.loads(manifest_data)
    records = [json.loads(line) for line in data.splitlines() if line.strip()]
    if manifest.get("dataset_version_id") != version.id or len(records) != version.sample_count:
        raise ValueError("MATERIALIZATION_HASH_MISMATCH")
    by_id = {row["metadata"]["sample_id"]: row for row in records}
    if len(by_id) != len(records):
        raise ValueError("MATERIALIZATION_HASH_MISMATCH")
    return manifest, by_id


def compare(
    session: Session,
    workspace_id: str,
    actor_id: str,
    left_id: str,
    right_id: str,
    settings: Settings | None = None,
) -> DatasetVersionComparison:
    left_build, left_dataset, left = scope_target(session, workspace_id, "dataset_version", left_id)
    right_build, right_dataset, right = scope_target(
        session, workspace_id, "dataset_version", right_id
    )
    assert left and right
    if left.dataset_id != right.dataset_id:
        raise ValueError("PRODUCT_MISMATCH")
    lock(session, f"quality-compare:{left_id}:{right_id}")
    existing = session.scalar(
        select(DatasetVersionComparison).where(
            DatasetVersionComparison.workspace_id == workspace_id,
            DatasetVersionComparison.left_version_id == left_id,
            DatasetVersionComparison.right_version_id == right_id,
        )
    )
    if existing:
        return existing
    a = stable_samples(session, left_build, left_dataset, left)
    b = stable_samples(session, right_build, right_dataset, right)
    manifest_diff: dict[str, Any] = {
        "status": "NOT_EVALUATED",
        "reason": "object storage not provided",
    }
    if settings:
        old_manifest, old_records = read_release(settings, left)
        new_manifest, new_records = read_release(settings, right)
        for rows, records, product in [
            (a, old_records, left_dataset.product_type),
            (b, new_records, right_dataset.product_type),
        ]:
            if {row["sample_id"] for row in rows} != set(records):
                raise ValueError("MATERIALIZATION_HASH_MISMATCH")
            for row in rows:
                row["content_hash"] = digest(sample_text(product, records[row["sample_id"]]))
        manifest_diff = {
            "status": "MEASURED",
            "fields": {
                key: {"left": old_manifest.get(key), "right": new_manifest.get(key)}
                for key in sorted(set(old_manifest) | set(new_manifest))
                if old_manifest.get(key) != new_manifest.get(key)
            },
        }
    payload = diff_samples(a, b)
    payload["manifest_diff"] = manifest_diff
    reports = [
        session.scalar(
            select(DatasetQualityReport)
            .where(DatasetQualityReport.dataset_version_id == version.id)
            .order_by(DatasetQualityReport.created_at.desc())
        )
        for version in [left, right]
    ]
    comparable = bool(
        all(reports)
        and reports[0]
        and reports[1]
        and reports[0].report_json.get("rule_config_hash")
        == reports[1].report_json.get("rule_config_hash")
        and left.tokenizer_version == right.tokenizer_version
    )
    metric_changes = []
    if comparable and reports[0] and reports[1]:
        old_metrics = {m["metric_id"]: m for m in reports[0].report_json["metrics"]}
        for new in reports[1].report_json["metrics"]:
            old = old_metrics.get(new["metric_id"])
            if (
                old
                and old["value"] is not None
                and new["value"] is not None
                and old["metric_version"] == new["metric_version"]
            ):
                metric_changes.append(
                    {
                        "metric_id": new["metric_id"],
                        "left": old["value"],
                        "right": new["value"],
                        "delta": new["value"] - old["value"],
                    }
                )
    payload.update(
        {
            "left_version_id": left_id,
            "right_version_id": right_id,
            "token_count_delta": right.token_count - left.token_count
            if left.tokenizer_version == right.tokenizer_version
            else None,
            "tokenizer_comparable": left.tokenizer_version == right.tokenizer_version,
            "sample_count_delta": right.sample_count - left.sample_count,
            "quality_comparison": "COMPARABLE" if comparable else "NOT_COMPARABLE",
            "quality_reason": None
            if comparable
            else "missing report or different rule configuration/tokenizer",
            "quality_metric_changes": metric_changes,
            "report_ids": [row.id if row else None for row in reports],
            "rule_versions": [
                row.report_json.get("rule_version_id") if row else None for row in reports
            ],
            "config": {
                "left": left_build.config_json,
                "right": right_build.config_json,
                "changed": left_build.config_hash != right_build.config_hash,
            },
            "manifest": {
                "left_sha256": left.manifest_sha256,
                "right_sha256": right.manifest_sha256,
                "content_changed": left.content_sha256 != right.content_sha256,
            },
            "composition": {
                "left": ratios(session, workspace_id, left_id),
                "right": ratios(session, workspace_id, right_id),
            },
            "computed_at": datetime.now(UTC).isoformat(),
        }
    )
    comparison = DatasetVersionComparison(
        workspace_id=workspace_id,
        left_version_id=left_id,
        right_version_id=right_id,
        comparison_json=payload,
        created_by=actor_id,
    )
    session.add(comparison)
    session.flush()
    return comparison
