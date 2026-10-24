from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.adapters.storage import S3ObjectStore
from corpusflow.core.config import Settings
from corpusflow.db.models import (
    Asset,
    CandidateSample,
    Dataset,
    DatasetBuild,
    DatasetVersion,
    DatasetVersionArtifact,
    DatasetVersionSample,
    Document,
    DocumentVersion,
    LicenseGrant,
    LineageEdge,
    SampleReview,
    Segment,
    uid,
)
from corpusflow.worker.outbox import enqueue_delivery

TOKENIZER_VERSION = "builtin-whitespace-1"


class MaterializationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _split_for_source(source_id: str) -> str:
    bucket = int(hashlib.sha256(source_id.encode()).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "validation"
    return "test"


def _validate_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise MaterializationError("INVALID_SAMPLE_FORMAT", "messages must be a non-empty list")
    allowed = {"system", "user", "assistant"}
    result: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in allowed:
            raise MaterializationError("INVALID_SAMPLE_FORMAT", "message role is invalid")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise MaterializationError("INVALID_SAMPLE_FORMAT", "message content is empty")
        result.append({"role": str(message["role"]), "content": content})
    return result


def _validate_product_payload(product_type: str, payload: dict[str, Any]) -> None:
    if product_type == "sft":
        _validate_messages(payload)
        return
    if product_type == "pretrain":
        if not isinstance(payload.get("text"), str) or not payload["text"].strip():
            raise MaterializationError("INVALID_SAMPLE_FORMAT", "pretrain text is empty")
        return
    if product_type == "rag":
        required = ("text", "source_id", "segment_id", "document_version_id", "location")
        if any(not payload.get(key) for key in required):
            raise MaterializationError("INVALID_SAMPLE_FORMAT", "rag chunk metadata is incomplete")
        return
    if product_type == "evaluation":
        evaluation_required = ("question", "reference_answer", "evidence_ids", "source_ids")
        if any(not payload.get(key) for key in evaluation_required):
            raise MaterializationError("INVALID_SAMPLE_FORMAT", "evaluation evidence is incomplete")
        if not isinstance(payload["evidence_ids"], list) or not isinstance(
            payload["source_ids"], list
        ):
            raise MaterializationError(
                "INVALID_SAMPLE_FORMAT", "evaluation evidence schema is invalid"
            )
        return
    raise MaterializationError("UNSUPPORTED_PRODUCT_TYPE", product_type)


def _payload_evidence_ids(product_type: str, payload: dict[str, Any]) -> list[str]:
    if isinstance(payload.get("evidence_ids"), list):
        return [str(item) for item in payload["evidence_ids"]]
    if product_type == "rag" and payload.get("segment_id"):
        return [str(payload["segment_id"])]
    return [str(item) for item in payload.get("metadata", {}).get("segment_ids", [])]


def _payload_token_count(product_type: str, payload: dict[str, Any]) -> int:
    if product_type == "sft":
        return sum(len(message["content"].split()) for message in payload["messages"])
    if product_type in {"pretrain", "rag"}:
        return len(str(payload.get("text", "")).split())
    text = f"{payload.get('question', '')} {payload.get('reference_answer', '')}"
    return len(text.split())


def materialize(
    session: Session,
    settings: Settings,
    workspace_id: str,
    dataset: Dataset,
    build: DatasetBuild,
    samples: list[CandidateSample],
    publisher_id: str,
    version_label: str,
) -> tuple[DatasetVersion, list[str]]:
    if not samples:
        raise MaterializationError("RELEASE_GATE_FAILED", "no approved samples")
    if _digest(build.config_json) != build.config_hash:
        raise MaterializationError(
            "BUILD_SNAPSHOT_CHANGED", "build configuration hash does not match snapshot"
        )
    expected_validation = _digest(
        {
            "config_hash": build.config_hash,
            "samples": sorted((s.id, s.payload_hash, s.status) for s in samples),
        }
    )
    if build.validated_snapshot_hash != expected_validation:
        raise MaterializationError(
            "BUILD_SNAPSHOT_CHANGED", "build snapshot changed after validation"
        )
    product_type = str(dataset.product_type)
    purpose = str(build.config_json.get("purpose", "training"))
    split_rows: list[
        tuple[CandidateSample, str, list[dict[str, str]], list[str], Segment, list[str]]
    ] = []
    for sample in samples:
        reviews = session.scalars(
            select(SampleReview).where(
                SampleReview.candidate_sample_id == sample.id,
                SampleReview.decision == "approved",
            )
        ).all()
        if sample.status != "approved" or not reviews:
            raise MaterializationError("SAMPLE_NOT_APPROVED", f"sample {sample.id} is not approved")
        if any(review.reviewer_id == publisher_id for review in reviews):
            raise MaterializationError("SELF_APPROVAL_FORBIDDEN", "publisher reviewed a sample")
        _validate_product_payload(product_type, sample.payload)
        evidence_ids = _payload_evidence_ids(product_type, sample.payload)
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise MaterializationError(
                "INVALID_SAMPLE_EVIDENCE", f"sample {sample.id} lacks evidence"
            )
        evidence = [
            session.scalar(
                select(Segment).where(
                    Segment.id == str(segment_id), Segment.workspace_id == workspace_id
                )
            )
            for segment_id in evidence_ids
        ]
        if any(segment is None for segment in evidence):
            raise MaterializationError(
                "INVALID_SAMPLE_EVIDENCE", f"sample {sample.id} has missing evidence"
            )
        segment = evidence[0]
        assert segment is not None
        if any(
            item.document_version_id != segment.document_version_id for item in evidence if item
        ):
            raise MaterializationError(
                "INVALID_SAMPLE_EVIDENCE", f"sample {sample.id} crosses document versions"
            )
        if sample.source_id != segment.source_id:
            raise MaterializationError(
                "INVALID_SAMPLE_EVIDENCE", f"sample {sample.id} source mismatch"
            )
        asset = session.scalar(
            select(Asset)
            .join(Document, Document.asset_id == Asset.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                DocumentVersion.id == segment.document_version_id,
                Asset.workspace_id == workspace_id,
            )
        )
        grant = session.scalar(
            select(LicenseGrant).where(
                LicenseGrant.workspace_id == workspace_id,
                LicenseGrant.asset_id == (asset.id if asset else ""),
                LicenseGrant.purpose == purpose,
                LicenseGrant.status == "confirmed",
            )
        )
        if not asset or not grant:
            raise MaterializationError(
                "PURPOSE_GRANT_MISSING", f"sample {sample.id} has no {purpose} grant"
            )
        messages = _validate_messages(sample.payload) if product_type == "sft" else []
        split_rows.append(
            (
                sample,
                _split_for_source(sample.source_id)
                if product_type in {"sft", "pretrain"}
                else "all",
                messages if product_type == "sft" else [],
                [str(x) for x in evidence_ids],
                segment,
                sorted({review.reviewer_id for review in reviews}),
            )
        )

    version_id = uid()
    lines: list[bytes] = []
    manifest_samples: list[dict[str, Any]] = []
    counts = {"train": 0, "validation": 0, "test": 0, "all": 0}
    token_count = 0
    input_references: list[dict[str, str]] = []
    for sample, split, messages, evidence_ids, segment, reviewer_ids in split_rows:
        record: dict[str, Any]
        if product_type == "sft":
            record = {"messages": messages, "metadata": {}}
        else:
            record = dict(sample.payload)
            record.setdefault("metadata", {})
        record["metadata"] = {
            **(record.get("metadata") or {}),
            "sample_id": sample.id,
            "source_id": sample.source_id,
            "evidence_ids": evidence_ids,
            "split": split,
        }
        encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        lines.append(encoded)
        counts[split] += 1
        token_count += _payload_token_count(product_type, sample.payload)
        manifest_samples.append(
            {
                "sample_id": sample.id,
                "source_id": sample.source_id,
                "segment_ids": evidence_ids,
                "document_version_id": segment.document_version_id,
                "split": split,
                "payload_sha256": sample.payload_hash,
                "quality": "approved",
                "reviewer_ids": reviewer_ids,
                "purpose": purpose,
            }
        )
        input_references.append(
            {
                "source_id": segment.source_id,
                "document_version_id": segment.document_version_id,
                "segment_id": segment.id,
            }
        )
    content = b"".join(lines)
    content_sha256 = hashlib.sha256(content).hexdigest()
    content_key = f"datasets/{dataset.id}/versions/{version_label}/dataset.jsonl"
    manifest = {
        "dataset_id": dataset.id,
        "dataset_version_id": version_id,
        "build_id": build.id,
        "build_config": build.config_json,
        "build_config_hash": build.config_hash,
        "product_type": product_type,
        "schema_version": str(build.config_json.get("schema_version", f"{product_type}.v1")),
        "purpose": purpose,
        "authorization": {"purpose": purpose, "status": "confirmed"},
        "quality_report": {
            "status": "approved",
            "approved_sample_count": len(lines),
            "review_records": [
                {"sample_id": sample.id, "reviewer_ids": reviewer_ids}
                for sample, _, _, _, _, reviewer_ids in split_rows
            ],
        },
        "input_references": input_references,
        "samples": manifest_samples,
        "sample_count": len(lines),
        "split_counts": counts,
        "token_count": token_count,
        "tokenizer_version": TOKENIZER_VERSION,
        "content": {"storage_key": content_key, "sha256": content_sha256, "bytes": len(content)},
        "published_by": publisher_id,
        "published_at": datetime.now(UTC).isoformat(),
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_key = f"datasets/{dataset.id}/versions/{version_label}/manifest.json"
    staging_id = uuid4().hex
    staging_content_key = f"staging/datasets/{version_id}/{staging_id}.jsonl"
    staging_manifest_key = f"staging/datasets/{version_id}/{staging_id}.manifest.json"
    store = S3ObjectStore(
        settings.object_store_endpoint,
        settings.object_store_bucket,
        settings.object_store_access_key.get_secret_value(),
        settings.object_store_secret_key.get_secret_value(),
    )
    staging_keys = [staging_content_key, staging_manifest_key]
    written = list(staging_keys)
    try:
        try:
            if store.exists(content_key) or store.exists(manifest_key):
                raise MaterializationError(
                    "VERSION_CONFLICT", "immutable version object already exists"
                )
            store.put(staging_content_key, content, "application/x-ndjson")
            store.put(staging_manifest_key, manifest_bytes, "application/json")
            if hashlib.sha256(store.get(staging_content_key)).hexdigest() != content_sha256:
                raise MaterializationError(
                    "MATERIALIZATION_HASH_MISMATCH", "staging JSONL hash mismatch"
                )
            store.put(content_key, content, "application/x-ndjson")
            store.put(manifest_key, manifest_bytes, "application/json")
        except MaterializationError:
            raise
        except Exception as exc:
            raise MaterializationError("ADAPTER_UNAVAILABLE", "object storage unavailable") from exc
        written.extend([content_key, manifest_key])
        version = DatasetVersion(
            id=version_id,
            workspace_id=workspace_id,
            dataset_id=dataset.id,
            build_id=build.id,
            version=version_label,
            manifest_sha256=manifest_sha256,
            content_sha256=content_sha256,
            status="published",
            published_by=publisher_id,
            manifest_storage_key=manifest_key,
            content_storage_key=content_key,
            content_bytes=len(content),
            sample_count=len(lines),
            train_count=counts["train"],
            validation_count=counts["validation"],
            test_count=counts["test"],
            token_count=token_count,
            tokenizer_version=TOKENIZER_VERSION,
            published_at=datetime.now(UTC),
        )
        session.add(version)
        session.flush()
        session.add(
            DatasetVersionArtifact(
                workspace_id=workspace_id,
                dataset_version_id=version.id,
                kind="dataset_jsonl",
                storage_key=content_key,
                content_sha256=content_sha256,
                byte_size=len(content),
                immutable=True,
            )
        )
        session.add(
            DatasetVersionArtifact(
                workspace_id=workspace_id,
                dataset_version_id=version.id,
                kind="manifest_json",
                storage_key=manifest_key,
                content_sha256=manifest_sha256,
                byte_size=len(manifest_bytes),
                immutable=True,
            )
        )
        for sample, split, _, evidence_ids, segment, _reviewer_ids in split_rows:
            session.add(
                DatasetVersionSample(
                    dataset_version_id=version.id, candidate_sample_id=sample.id, split=split
                )
            )
            session.add(
                LineageEdge(
                    workspace_id=workspace_id,
                    from_type="CandidateSample",
                    from_id=sample.id,
                    to_type="DatasetVersion",
                    to_id=version.id,
                    relation="included_in",
                )
            )
            for evidence_id in evidence_ids:
                session.add(
                    LineageEdge(
                        workspace_id=workspace_id,
                        from_type="Segment",
                        from_id=evidence_id,
                        to_type="DatasetVersion",
                        to_id=version.id,
                        relation="materialized_in",
                    )
                )
            session.add(
                LineageEdge(
                    workspace_id=workspace_id,
                    from_type="Source",
                    from_id=segment.source_id,
                    to_type="DatasetVersion",
                    to_id=version.id,
                    relation="contributed_to",
                )
            )
        enqueue_delivery(session, workspace_id, version.id)
        build.status = "published"
        return version, written
    except Exception:
        # Final immutable keys may belong to a concurrent successful publisher.
        # The outer API transaction owns cleanup after a commit failure; this
        # scope only removes staging objects that this attempt created.
        for key in staging_keys:
            try:
                store.delete(key)
            except Exception:
                pass
        raise
