"""Approved plan -> real bytes -> Asset; acquisition never creates purpose grants."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.adapters.acquisition import AcquisitionError, SafeFetcher, approved_target
from corpusflow.adapters.storage import S3ObjectStore
from corpusflow.core.config import Settings
from corpusflow.db.models import (
    Asset,
    AssetBlob,
    DiscoveryCandidate,
    IngestPlan,
    LineageEdge,
    Membership,
    Source,
    User,
    uid,
)
from corpusflow.services import rag
from corpusflow.services.quality_governance import lock


def create(
    session: Session,
    settings: Settings,
    wid: str,
    actor: str,
    source: str,
    ids: list[str],
    key: str,
) -> IngestPlan:
    lock(session, f"ingest-plan:{wid}:{key}")
    rag.require(
        session.scalar(select(Source.id).where(Source.id == source, Source.workspace_id == wid)),
        "NOT_FOUND",
    )
    entries = []
    for cid in ids:
        candidate = session.scalar(
            select(DiscoveryCandidate).where(
                DiscoveryCandidate.id == cid, DiscoveryCandidate.workspace_id == wid
            )
        )
        rag.require(candidate, "NOT_FOUND")
        assert candidate is not None
        approved_target(candidate.url, settings.acquisition_hosts)
        entries.append({"candidate_id": cid, "url": candidate.url, "title": candidate.title})
    snapshot = {"schema": "ingest-plan.v1", "entries": entries, "purpose_grants": "NONE"}
    existing = session.scalar(
        select(IngestPlan).where(IngestPlan.workspace_id == wid, IngestPlan.request_key == key)
    )
    if existing:
        rag.require(
            existing.source_id == source and existing.config_snapshot == snapshot,
            "IDEMPOTENCY_KEY_REUSED",
        )
        return existing
    row = IngestPlan(
        workspace_id=wid,
        source_id=source,
        created_by=actor,
        request_key=key,
        config_snapshot=snapshot,
    )
    session.add(row)
    session.flush()
    return row


def reviewer_allowed(session: Session, row: IngestPlan) -> bool:
    return bool(
        session.scalar(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.workspace_id == row.workspace_id,
                Membership.user_id == row.reviewed_by,
                Membership.role.in_(["admin", "reviewer"]),
                Membership.status == "active",
                User.disabled.is_(False),
            )
        )
    )


def execute(session: Session, settings: Settings, row: IngestPlan) -> None:
    rag.member(session, row.workspace_id, row.created_by, True)
    rag.require(
        row.reviewed_by != row.created_by and reviewer_allowed(session, row), "PERMISSION_DENIED"
    )
    store = S3ObjectStore(
        settings.object_store_endpoint,
        settings.object_store_bucket,
        settings.object_store_access_key.get_secret_value(),
        settings.object_store_secret_key.get_secret_value(),
    )
    entries = row.config_snapshot["entries"]
    for entry in entries[len(row.results) :]:
        # Recheck administrator allowlist after review, not only when planning.
        result = SafeFetcher(settings.acquisition_hosts).get(entry["url"])
        if result.media_type == "application/pdf" and result.content.startswith(b"%PDF-"):
            suffix = "pdf"
        elif result.media_type in {"text/html", "application/xhtml+xml"}:
            suffix = "html"
        else:
            raise AcquisitionError("ACQUISITION_FORMAT_REJECTED")
        object_key = (
            f"acquisition/{row.workspace_id}/{row.id}/"
            f"{entry['candidate_id']}/{result.sha256}.{suffix}"
        )
        # Conditional object write protects retries and unexpected URL content changes.
        client = store._client()
        try:
            try:
                client.put_object(
                    Bucket=store.bucket,
                    Key=object_key,
                    Body=result.content,
                    ContentType=result.media_type,
                    IfNoneMatch="*",
                )
            except Exception as exc:
                if (
                    getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
                    != 412
                ):
                    raise
                if store.get(object_key) != result.content:
                    raise AcquisitionError("ACQUISITION_HASH_MISMATCH") from None
        finally:
            client.close()
        blob = AssetBlob(
            id=uid(),
            workspace_id=row.workspace_id,
            storage_key=object_key,
            sha256=result.sha256,
            byte_size=len(result.content),
            media_type=result.media_type,
        )
        session.add(blob)
        session.flush()
        asset = Asset(
            id=uid(),
            workspace_id=row.workspace_id,
            source_id=row.source_id,
            blob_id=blob.id,
            filename=f"{entry['candidate_id']}.{suffix}",
            format=suffix,
            metadata_json={
                "origin_url": entry["url"],
                "ingest_plan_id": row.id,
                "candidate_id": entry["candidate_id"],
                "license_status": "pending",
            },
        )
        session.add(asset)
        session.flush()
        for kind, oid, relation in [
            ("DiscoveryCandidate", entry["candidate_id"], "acquired"),
            ("IngestPlan", row.id, "registered"),
            ("Source", row.source_id, "contains"),
        ]:
            session.add(
                LineageEdge(
                    workspace_id=row.workspace_id,
                    from_type=kind,
                    from_id=oid,
                    to_type="Asset",
                    to_id=asset.id,
                    relation=relation,
                )
            )
        row.results = [
            *row.results,
            {
                "candidate_id": entry["candidate_id"],
                "asset_id": asset.id,
                "sha256": result.sha256,
                "bytes": len(result.content),
                "object_key": object_key,
                "elapsed_ms": result.elapsed_ms,
                "purpose_grants": "NONE",
            },
        ]
    row.status = "succeeded"


def serialize(row: IngestPlan) -> dict[str, Any]:
    return {
        "plan_id": row.id,
        "status": row.status,
        "config": row.config_snapshot,
        "created_by": row.created_by,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "results": row.results,
        "error_code": row.error_code,
    }
