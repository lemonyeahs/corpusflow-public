"""P0 business API.

Routers stay thin: persistence and policy decisions live in the functions in
this module, which keeps the same authorization and transition rules usable by
the worker and future UI adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import boto3
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from corpusflow.adapters.parser.base import ParserError
from corpusflow.adapters.parser.docx import DOCXParserAdapter
from corpusflow.api.dependencies import actor_id as actor_id
from corpusflow.api.dependencies import db as db
from corpusflow.api.dependencies import role_required as role_required
from corpusflow.api.dependencies import workspace_id as workspace_id
from corpusflow.db.models import (
    Artifact,
    Asset,
    AssetBlob,
    AuditEvent,
    BuildInput,
    CandidateSample,
    Dataset,
    DatasetBuild,
    DatasetQualityReport,
    DatasetVersion,
    DatasetVersionComparison,
    DatasetVersionSample,
    DiscoveryCandidate,
    Document,
    DocumentMetadata,
    DocumentVersion,
    IngestBatch,
    IngestItem,
    LicenseEvidence,
    LicenseGrant,
    LineageEdge,
    Membership,
    MetadataProposal,
    NodeRun,
    OperatorDefinition,
    OutboxEvent,
    PipelineRun,
    PipelineTemplate,
    PipelineVersion,
    PreferenceAnnotation,
    PreferenceSample,
    ProcessingBatch,
    QualityEvaluationRun,
    QualityIssue,
    QualityMetricResult,
    QualityReview,
    QualityRuleVersion,
    SampleEvidence,
    SampleReview,
    Segment,
    Source,
    UploadSession,
    User,
    Workspace,
    uid,
)
from corpusflow.services.dataset_builders import BuilderError, DpoBuilder, builder_for
from corpusflow.services.dataset_materializer import MaterializationError, materialize
from corpusflow.services.quality_governance import (
    METRICS,
    default_rule_set,
)
from corpusflow.services.quality_governance import (
    compare as compare_quality_versions,
)
from corpusflow.services.quality_governance import (
    coverage as quality_coverage,
)
from corpusflow.services.quality_governance import (
    evaluate as evaluate_quality,
)
from corpusflow.services.quality_governance import (
    ratios as quality_ratios,
)
from corpusflow.services.quality_rework import prepare_rework
from corpusflow.worker.outbox import enqueue_run

router = APIRouter(prefix="/api/v1", tags=["business"])


def audit(
    session: Session,
    request: Request,
    workspace: str,
    user: str,
    action: str,
    typ: str,
    rid: str,
    summary: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            workspace_id=workspace,
            actor_id=user,
            action=action,
            resource_type=typ,
            resource_id=rid,
            request_id=request.state.request_id,
            summary=summary or {},
        )
    )


def edge(
    session: Session, workspace: str, ft: str, fid: str, tt: str, tid: str, relation: str
) -> None:
    session.add(
        LineageEdge(
            workspace_id=workspace,
            from_type=ft,
            from_id=fid,
            to_type=tt,
            to_id=tid,
            relation=relation,
        )
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def extract_metadata(
    filename: str, media_type: str, content: bytes
) -> tuple[dict[str, Any], dict[str, Any], dict[str, float]]:
    """Deterministic local extraction. It never calls an external model or API."""
    name = filename.lower()
    raw = content.decode("utf-8", "ignore")
    if name.endswith(".docx") or media_type.split(";", 1)[0] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        # ZIP headers are not document text and can contain NULs rejected by JSONB.
        try:
            raw = DOCXParserAdapter().parse(content, filename, media_type).text
        except ParserError:
            # Preserve the upload; the Worker reports malformed documents explicitly.
            raw = ""
    pdf_text = content.decode("latin-1", "ignore") if name.endswith(".pdf") else raw
    text_value = pdf_text if name.endswith(".pdf") else raw
    title: str | None = None
    if name.endswith(".md") or name.endswith(".markdown"):
        match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        title = match.group(1).strip() if match else None
    elif name.endswith(".html") or name.endswith(".htm"):
        match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else None
    elif name.endswith(".json"):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                title = str(value.get("title") or value.get("name") or "") or None
        except json.JSONDecodeError:
            pass
    else:
        match = re.search(r"(?:/Title\s*\(([^)]{2,300})\)|^\s*([^\n]{8,200})\s*$)", pdf_text, re.M)
        title = (match.group(1) or match.group(2)).strip() if match else None
    doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text_value, re.I)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text_value)
    abstract_match = re.search(
        r"(?:abstract|摘要)\s*[:：]?\s*(.{80,2000}?)(?:\n\s*\n|keywords|关键词|introduction|引言)",
        raw,
        re.I | re.S,
    )
    authors_match = re.search(r"(?:authors?|作者)\s*[:：]\s*([^\n]{2,500})", raw, re.I)
    extension = name.rsplit(".", 1)[-1] if "." in name else "other"
    format_name = {"markdown": "md", "htm": "html"}.get(extension, extension)
    if content.startswith(b"%PDF"):
        format_name = "pdf"
        media_type = "application/pdf"
    elif content.lstrip().startswith((b"<!DOCTYPE html", b"<html", b"<HTML")):
        format_name = "html"
        media_type = "text/html"
    elif name.endswith(".jsonl") or media_type.split(";", 1)[0] in {
        "application/jsonl",
        "application/x-ndjson",
    }:
        format_name = "jsonl"
        media_type = "application/x-ndjson"
    elif content.lstrip().startswith((b"{", b"[")):
        format_name = "json"
        media_type = "application/json"
    business_type = "unidentified"
    lower = text_value.lower()
    if any(token in lower for token in ("doi.org/", "abstract", "references", "摘要", "关键词")):
        business_type = "academic_paper"
    elif "technical report" in lower or "技术报告" in text_value:
        business_type = "technical_report"
    elif format_name in {"md", "html", "txt", "json"}:
        business_type = "technical_document"
    fields: dict[str, Any] = {
        "format": format_name,
        "mime_type": media_type,
        "filename": filename,
        "size": len(content),
        "title": title,
        "authors": [
            item.strip() for item in re.split(r"[,;，；]", authors_match.group(1)) if item.strip()
        ]
        if authors_match
        else [],
        "abstract": abstract_match.group(1).strip() if abstract_match else None,
        "doi": doi_match.group(0).rstrip(".,;") if doi_match else None,
        "publication_year": int(year_match.group(1)) if year_match else None,
        "document_type": business_type,
        "language": "zh" if len(re.findall(r"[\u4e00-\u9fff]", text_value)) > 20 else "en",
        "keywords": [],
    }
    sources = {
        key: (
            "builtin:file-signature"
            if key in {"format", "mime_type", "size", "filename"}
            else "builtin:text-heuristic"
        )
        for key in fields
    }
    confidence = {
        key: (
            0.98
            if key in {"format", "mime_type", "size", "filename"}
            else 0.65
            if fields[key]
            else 0.0
        )
        for key in fields
    }
    return fields, sources, confidence


def store_bytes(request: Request, key: str, content: bytes, content_type: str) -> None:
    config = request.app.state.config
    client = boto3.client(
        "s3",
        endpoint_url=config.object_store_endpoint,
        aws_access_key_id=config.object_store_access_key.get_secret_value(),
        aws_secret_access_key=config.object_store_secret_key.get_secret_value(),
        region_name="us-east-1",
    )
    try:
        client.put_object(
            Bucket=config.object_store_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
    except Exception as exc:
        raise HTTPException(503, "ADAPTER_UNAVAILABLE") from exc
    finally:
        client.close()


def current_grant(
    session: Session, workspace: str, asset_id: str, purpose: str
) -> LicenseGrant | None:
    grant = session.scalar(
        select(LicenseGrant)
        .where(
            LicenseGrant.workspace_id == workspace,
            LicenseGrant.asset_id == asset_id,
            LicenseGrant.purpose == purpose,
        )
        .order_by(LicenseGrant.created_at.desc())
    )
    if not grant or grant.status != "confirmed":
        return None
    return grant


class SessionIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    workspace_name: str = Field(default="Default Workspace", min_length=1, max_length=200)


@router.post("/auth/session")
def create_session(body: SessionIn, session: Session = Depends(db)):
    user = session.scalar(select(User).where(User.oidc_sub == body.user_id))
    if not user:
        user = User(oidc_sub=body.user_id, display_name=body.display_name)
        session.add(user)
        session.flush()
    slug = re.sub(r"[^a-z0-9]+", "-", body.workspace_name.lower()).strip("-") or "workspace"
    workspace = session.scalar(
        select(Workspace).where(Workspace.slug.in_([slug, f"{slug}-{user.id[:8]}"]))
    )
    if not workspace:
        workspace = Workspace(slug=f"{slug}-{user.id[:8]}", name=body.workspace_name)
        session.add(workspace)
        session.flush()
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.workspace_id == workspace.id
        )
    )
    if not membership:
        session.add(Membership(user_id=user.id, workspace_id=workspace.id, role="admin"))
    session.commit()
    return {
        "token": user.oidc_sub,
        "user_id": user.id,
        "workspace_id": workspace.id,
        "role": "admin",
    }


@router.get("/auth/me")
def me(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    memberships = session.scalars(select(Membership).where(Membership.user_id == user)).all()
    return {
        "user_id": user,
        "workspaces": [{"workspace_id": m.workspace_id, "role": m.role} for m in memberships],
    }


@router.get("/workspaces")
def workspaces(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    rows = session.scalars(
        select(Membership).where(Membership.user_id == user, Membership.status == "active")
    ).all()
    return {"items": [{"workspace_id": m.workspace_id, "role": m.role} for m in rows]}


@router.get("/sources")
def sources(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = session.scalars(
        select(Source).where(Source.workspace_id == wid).order_by(Source.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "source_id": row.id,
                "name": row.name,
                "kind": row.kind,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


class MemberIn(BaseModel):
    user_id: str
    role: str = Field(pattern="^(admin|engineer|reviewer|viewer)$")


@router.post("/workspaces/{wid}/members")
def add_member(wid: str, body: MemberIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    role_required(session, user, wid, {"admin"})
    target = session.scalar(select(User).where(User.oidc_sub == body.user_id))
    if not target:
        raise HTTPException(404, "NOT_FOUND")
    membership = session.scalar(
        select(Membership).where(Membership.user_id == target.id, Membership.workspace_id == wid)
    )
    if membership:
        membership.role = body.role
    else:
        session.add(Membership(user_id=target.id, workspace_id=wid, role=body.role))
    audit(session, request, wid, user, "member.upsert", "workspace", wid)
    session.commit()
    return {"workspace_id": wid, "user_id": target.id, "role": body.role}


class EvidenceIn(BaseModel):
    uri: str
    legal_basis: str


class GrantIn(BaseModel):
    asset_id: str
    purpose: str = Field(pattern="^(research|training|rag|evaluation|redistribute)$")
    evidence_uri: str
    legal_basis: str


@router.post("/authorization/grants")
def grant(body: GrantIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    asset = session.scalar(
        select(Asset).where(Asset.id == body.asset_id, Asset.workspace_id == wid)
    )
    if not asset:
        raise HTTPException(404, "NOT_FOUND")
    evidence = LicenseEvidence(
        workspace_id=wid,
        source_id=asset.source_id,
        asset_id=asset.id,
        uri=body.evidence_uri,
        legal_basis=body.legal_basis,
        reviewed_by=user,
    )
    session.add(evidence)
    session.flush()
    row = LicenseGrant(
        workspace_id=wid,
        asset_id=asset.id,
        purpose=body.purpose,
        status="confirmed",
        evidence_id=evidence.id,
        reason="confirmed with evidence",
    )
    session.add(row)
    session.flush()
    audit(
        session,
        request,
        wid,
        user,
        "license.grant.confirm",
        "asset",
        asset.id,
        {"purpose": body.purpose},
    )
    session.commit()
    return {"grant_id": row.id, "asset_id": asset.id, "purpose": body.purpose, "status": row.status}


class DecisionIn(BaseModel):
    asset_ids: list[str]
    purpose: str = Field(pattern="^(research|training|rag|evaluation|redistribute)$")
    action: str = "use"


@router.post("/authorization/decisions")
def decisions(body: DecisionIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    result = []
    for aid in body.asset_ids:
        asset = session.scalar(select(Asset).where(Asset.id == aid, Asset.workspace_id == wid))
        allowed = bool(asset and current_grant(session, wid, aid, body.purpose))
        result.append(
            {
                "asset_id": aid,
                "allow": allowed,
                "reason": "grant_confirmed" if allowed else "grant_missing",
                "policy_version": "p0-1",
            }
        )
    audit(
        session,
        request,
        wid,
        user,
        "authorization.evaluate",
        "workspace",
        wid,
        {"purpose": body.purpose},
    )
    session.commit()
    return {"purpose": body.purpose, "decisions": result}


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="upload", min_length=1, max_length=50)


@router.post("/sources")
def source(body: SourceIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    row = Source(workspace_id=wid, name=body.name, kind=body.kind)
    session.add(row)
    session.commit()
    return {"source_id": row.id, "name": row.name}


class CandidateIn(BaseModel):
    title: str
    url: str


@router.post("/discovery-candidates")
def candidate(body: CandidateIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    parsed = urlparse(body.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(422, "INVALID_ARGUMENT")
    row = DiscoveryCandidate(workspace_id=wid, title=body.title, url=body.url)
    session.add(row)
    session.flush()
    audit(session, request, wid, user, "candidate.create", "candidate", row.id)
    session.commit()
    return {"candidate_id": row.id, "state": row.state}


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f]+$")
    size: int = Field(ge=0, le=1024 * 1024 * 1024)
    content_type: str = "application/octet-stream"


@router.post("/uploads/init")
def upload_init(body: UploadIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    row = UploadSession(
        workspace_id=wid,
        filename=body.filename,
        declared_size=body.size,
        content_type=body.content_type,
        status="uploading",
        object_key=f"uploads/{uid()}/{body.filename}",
    )
    session.add(row)
    session.flush()
    audit(session, request, wid, user, "upload.init", "upload", row.id)
    session.commit()
    return {
        "upload_id": row.id,
        "status": row.status,
        "object_key": row.object_key,
        "upload_url": f"/api/v1/uploads/{row.id}/content",
    }


@router.put("/uploads/{upload_id}/content")
async def upload_content(upload_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(UploadSession).where(
            UploadSession.id == upload_id, UploadSession.workspace_id == wid
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    if row.status == "verified":
        return {
            "upload_id": row.id,
            "status": row.status,
            "bytes": row.declared_size,
            "sha256": row.checksum,
        }
    data = await request.body()
    if len(data) != row.declared_size:
        raise HTTPException(422, "UPLOAD_SIZE_MISMATCH")
    row.content = data
    row.checksum = hashlib.sha256(data).hexdigest()
    row.status = "uploaded"
    store_bytes(request, row.object_key or f"uploads/{row.id}", data, row.content_type)
    session.commit()
    return {
        "upload_id": row.id,
        "status": row.status,
        "bytes": len(data),
        "sha256": row.checksum,
    }


@router.post("/uploads/{upload_id}/content")
async def upload_content_post(upload_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(UploadSession).where(
            UploadSession.id == upload_id, UploadSession.workspace_id == wid
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    if row.status == "verified":
        return {
            "upload_id": row.id,
            "status": row.status,
            "bytes": row.declared_size,
            "sha256": row.checksum,
        }
    data = await request.body()
    if len(data) != row.declared_size:
        raise HTTPException(422, "UPLOAD_SIZE_MISMATCH")
    row.content = data
    row.checksum = hashlib.sha256(data).hexdigest()
    row.status = "uploaded"
    store_bytes(request, row.object_key or f"uploads/{row.id}", data, row.content_type)
    session.commit()
    return {"upload_id": row.id, "status": row.status, "bytes": len(data), "sha256": row.checksum}


class CompleteIn(BaseModel):
    checksum: str | None = Field(default=None, min_length=64, max_length=64)


@router.post("/uploads/{upload_id}/complete")
def upload_complete(
    upload_id: str, body: CompleteIn, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(UploadSession).where(
            UploadSession.id == upload_id, UploadSession.workspace_id == wid
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    if row.status == "verified" and (not body.checksum or body.checksum == row.checksum):
        return {"upload_id": row.id, "status": row.status, "sha256": row.checksum}
    if row.status != "uploaded":
        raise HTTPException(409, "INVALID_STATE_TRANSITION")
    if body.checksum and body.checksum != row.checksum:
        raise HTTPException(422, "CHECKSUM_MISMATCH")
    row.status = "verified"
    session.commit()
    return {"upload_id": row.id, "status": row.status, "sha256": row.checksum}


class BatchIn(BaseModel):
    upload_ids: list[str] = Field(min_length=1)
    source_id: str


@router.post("/ingest-batches")
def ingest_batch(body: BatchIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    src = session.scalar(
        select(Source).where(Source.id == body.source_id, Source.workspace_id == wid)
    )
    if not src:
        raise HTTPException(404, "NOT_FOUND")
    uploads = {
        row.id: row
        for row in session.scalars(
            select(UploadSession).where(
                UploadSession.id.in_(body.upload_ids), UploadSession.workspace_id == wid
            )
        ).all()
    }
    if len(uploads) != len(set(body.upload_ids)):
        raise HTTPException(404, "NOT_FOUND")
    batch = IngestBatch(workspace_id=wid, created_by=user, status="completed")
    session.add(batch)
    session.flush()
    for upload_id in body.upload_ids:
        up = uploads[upload_id]
        item = IngestItem(batch_id=batch.id, upload_session_id=upload_id)
        if not up or up.status != "verified":
            item.status = "failed"
            item.error_code = "UPLOAD_NOT_VERIFIED"
            session.add(item)
            continue
        blob = session.scalar(
            select(AssetBlob).where(AssetBlob.workspace_id == wid, AssetBlob.sha256 == up.checksum)
        )
        if not blob:
            blob = AssetBlob(
                workspace_id=wid,
                storage_key=up.object_key or f"uploads/{up.id}",
                sha256=up.checksum or "",
                byte_size=len(up.content or b""),
                media_type=up.content_type,
            )
            session.add(blob)
            session.flush()
        existing = session.scalar(
            select(Asset).where(Asset.workspace_id == wid, Asset.blob_id == blob.id)
        )
        if existing:
            item.status = "duplicate"
            item.asset_id = existing.id
        else:
            fields, field_sources, confidence = extract_metadata(
                up.filename, up.content_type, up.content or b""
            )
            asset = Asset(
                workspace_id=wid,
                source_id=src.id,
                blob_id=blob.id,
                filename=up.filename,
                format=str(fields.get("format") or "other"),
                language=fields.get("language"),
                ingestion_status="metadata_pending",
                metadata_json={"status": "pending", "document_type": fields.get("document_type")},
            )
            session.add(asset)
            session.flush()
            session.add(
                MetadataProposal(
                    workspace_id=wid,
                    asset_id=asset.id,
                    status="pending",
                    parser_name="builtin-metadata",
                    parser_version="1",
                    fields=fields,
                    field_sources=field_sources,
                    confidence=confidence,
                )
            )
            item.status = "succeeded"
            item.asset_id = asset.id
            edge(session, wid, "Source", src.id, "Asset", asset.id, "contains")
        session.add(item)
    session.flush()
    batch.totals = {
        "total": len(body.upload_ids),
        "succeeded": sum(
            1
            for i in session.scalars(
                select(IngestItem).where(IngestItem.batch_id == batch.id)
            ).all()
            if i.status == "succeeded"
        ),
        "failed": sum(
            1
            for i in session.scalars(
                select(IngestItem).where(IngestItem.batch_id == batch.id)
            ).all()
            if i.status == "failed"
        ),
    }
    audit(session, request, wid, user, "ingest.complete", "batch", batch.id)
    session.commit()
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "totals": batch.totals,
        "items": [
            {
                "upload_id": i.upload_session_id,
                "asset_id": i.asset_id,
                "status": i.status,
                "error_code": i.error_code,
            }
            for i in session.scalars(
                select(IngestItem).where(IngestItem.batch_id == batch.id)
            ).all()
        ],
    }


@router.get("/assets")
def assets(
    request: Request,
    session: Session = Depends(db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    file_format: str | None = None,
    query: str | None = None,
    metadata_status: str | None = None,
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    asset_query = select(Asset).where(Asset.workspace_id == wid)
    if file_format:
        asset_query = asset_query.where(Asset.format == file_format.lower())
    if query:
        asset_query = asset_query.where(Asset.filename.ilike(f"%{query}%"))
    if metadata_status == "pending":
        asset_query = asset_query.where(Asset.ingestion_status == "metadata_pending")
    rows = session.scalars(
        asset_query.order_by(Asset.created_at, Asset.id).offset(offset).limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(asset_query.subquery())) or 0
    return {
        "items": [
            {
                "asset_id": a.id,
                "filename": a.filename,
                "format": a.format,
                "source_id": a.source_id,
                "quality_status": a.quality_status,
                "ingestion_status": a.ingestion_status,
                "metadata_status": (a.metadata_json or {}).get("status", "pending"),
            }
            for a in rows
        ],
        "total_count": total,
    }


@router.get("/assets/stats")
def asset_stats(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    total = (
        session.scalar(select(func.count()).select_from(Asset).where(Asset.workspace_id == wid))
        or 0
    )
    return {
        "total_assets": total,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "metric_definition_version": "p0-1",
    }


@router.get("/dashboard/overview")
def dashboard_overview(
    request: Request,
    session: Session = Depends(db),
    source_id: str | None = None,
    file_format: str | None = None,
    asset_status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    """Return real, workspace-scoped lifecycle counts for the visitor dashboard.

    The response keeps entity units explicit. Assets, document versions, segments,
    candidate samples and published versions are never added together as if they
    were one funnel.
    """
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    asset_query = select(Asset).where(Asset.workspace_id == wid)
    if source_id:
        asset_query = asset_query.where(Asset.source_id == source_id)
    if file_format:
        asset_query = asset_query.where(Asset.format == file_format.lower())
    if asset_status:
        asset_query = asset_query.where(Asset.ingestion_status == asset_status)
    if since:
        asset_query = asset_query.where(Asset.created_at >= since)
    if until:
        asset_query = asset_query.where(Asset.created_at <= until)
    assets = list(session.scalars(asset_query).all())
    asset_ids = [row.id for row in assets]
    source_ids = sorted({row.source_id for row in assets})

    def count_rows(model: Any, *conditions: Any) -> int:
        query = select(func.count()).select_from(model).where(*conditions)
        return int(session.scalar(query) or 0)

    physical_files = (
        count_rows(
            AssetBlob, AssetBlob.workspace_id == wid, AssetBlob.id.in_([a.blob_id for a in assets])
        )
        if asset_ids
        else 0
    )
    unique_content = (
        int(
            session.scalar(
                select(func.count(func.distinct(AssetBlob.sha256)))
                .join(Asset, Asset.blob_id == AssetBlob.id)
                .where(Asset.workspace_id == wid, Asset.id.in_(asset_ids))
            )
            or 0
        )
        if asset_ids
        else 0
    )
    total_bytes = (
        int(
            session.scalar(
                select(func.coalesce(func.sum(AssetBlob.byte_size), 0))
                .join(Asset, Asset.blob_id == AssetBlob.id)
                .where(Asset.workspace_id == wid, Asset.id.in_(asset_ids))
            )
            or 0
        )
        if asset_ids
        else 0
    )
    format_distribution: dict[str, int] = {}
    business_distribution: dict[str, int] = {}
    for row in assets:
        fmt = (row.format or "unknown").lower()
        format_distribution[fmt] = format_distribution.get(fmt, 0) + 1
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        kind = str(
            metadata.get("document_type") or metadata.get("business_type") or "unclassified"
        ).lower()
        if kind in {"paper", "academic_paper", "论文", "journal_article", "conference_paper"}:
            kind = "paper"
        elif kind in {"technical_report", "技术报告"}:
            kind = "technical_report"
        elif kind in {"technical_document", "普通技术文档", "document"}:
            kind = "technical_document"
        elif kind in {"book", "书籍", "chapter"}:
            kind = "book"
        else:
            kind = "unclassified"
        business_distribution[kind] = business_distribution.get(kind, 0) + 1
    source_query = select(Source).where(Source.workspace_id == wid)
    if source_ids:
        source_query = source_query.where(Source.id.in_(source_ids))
    sources = list(session.scalars(source_query).all())
    document_query = select(Document).where(Document.workspace_id == wid)
    if asset_ids:
        document_query = document_query.where(Document.asset_id.in_(asset_ids))
    else:
        document_query = document_query.where(text("1=0"))
    documents = list(session.scalars(document_query).all())
    supported_formats = ("pdf", "md", "json", "html", "txt", "docx", "csv", "other")
    format_stats: dict[str, dict[str, Any]] = {}
    for fmt in supported_formats:
        matching = [row for row in assets if (row.format or "other").lower() == fmt]
        blob_ids = [row.blob_id for row in matching]
        sizes = (
            int(
                session.scalar(
                    select(func.coalesce(func.sum(AssetBlob.byte_size), 0)).where(
                        AssetBlob.id.in_(blob_ids)
                    )
                )
                or 0
            )
            if blob_ids
            else 0
        )
        matching_ids = {asset.id for asset in matching}
        format_stats[fmt] = {
            "count": len(matching),
            "bytes": sizes,
            "parse_succeeded": sum(
                1
                for doc in documents
                if doc.parse_status == "succeeded" and doc.asset_id in matching_ids
            ),
            "parse_failed": sum(
                1
                for doc in documents
                if doc.parse_status in {"failed", "error"} and doc.asset_id in matching_ids
            ),
            "last_uploaded_at": max((row.created_at.isoformat() for row in matching), default=None),
        }
    document_ids = [row.id for row in documents]
    version_query = select(DocumentVersion).where(DocumentVersion.workspace_id == wid)
    if document_ids:
        version_query = version_query.where(DocumentVersion.document_id.in_(document_ids))
    else:
        version_query = version_query.where(text("1=0"))
    versions = list(session.scalars(version_query).all())
    version_ids = [row.id for row in versions]
    segment_count = count_rows(
        Segment,
        Segment.workspace_id == wid,
        Segment.document_version_id.in_(version_ids) if version_ids else text("1=0"),
    )

    run_query = select(PipelineRun).where(PipelineRun.workspace_id == wid)
    if asset_ids:
        run_query = run_query.where(PipelineRun.asset_id.in_(asset_ids))
    else:
        run_query = run_query.where(text("1=0"))
    runs = list(session.scalars(run_query).all())
    run_status: dict[str, int] = {}
    failure_reasons: dict[str, int] = {}
    for row in runs:
        run_status[row.status] = run_status.get(row.status, 0) + 1
        if row.error_code:
            failure_reasons[row.error_code] = failure_reasons.get(row.error_code, 0) + 1

    issue_query = select(QualityIssue).where(QualityIssue.workspace_id == wid)
    if asset_ids:
        issue_query = issue_query.where(QualityIssue.asset_id.in_(asset_ids))
    else:
        issue_query = issue_query.where(text("1=0"))
    issues = list(session.scalars(issue_query).all())
    issue_status: dict[str, int] = {}
    for row in issues:
        issue_status[row.status] = issue_status.get(row.status, 0) + 1

    grant_query = select(LicenseGrant).where(LicenseGrant.workspace_id == wid)
    if asset_ids:
        grant_query = grant_query.where(LicenseGrant.asset_id.in_(asset_ids))
    else:
        grant_query = grant_query.where(text("1=0"))
    grant_status: dict[str, int] = {}
    for row in session.scalars(grant_query).all():
        key = f"{row.purpose}:{row.status}"
        grant_status[key] = grant_status.get(key, 0) + 1

    candidate_query = select(CandidateSample).where(CandidateSample.workspace_id == wid)
    candidates = list(session.scalars(candidate_query).all())
    candidate_status: dict[str, int] = {}
    for row in candidates:
        candidate_status[row.status] = candidate_status.get(row.status, 0) + 1

    version_rows = session.execute(
        select(DatasetVersion, Dataset.product_type, Dataset.name)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(DatasetVersion.workspace_id == wid)
        .order_by(DatasetVersion.created_at.desc())
    ).all()
    product_summary: dict[str, dict[str, int]] = {}
    recent_versions: list[dict[str, Any]] = []
    for version, product_type, name in version_rows:
        summary = product_summary.setdefault(
            product_type, {"versions": 0, "samples": 0, "published": 0}
        )
        summary["versions"] += 1
        summary["samples"] += int(version.sample_count or 0)
        if version.status == "published":
            summary["published"] += 1
        if len(recent_versions) < 12:
            recent_versions.append(
                {
                    "dataset_version_id": version.id,
                    "dataset_id": version.dataset_id,
                    "name": name,
                    "product_type": product_type,
                    "version": version.version,
                    "status": version.status,
                    "sample_count": version.sample_count,
                    "published_at": version.published_at.isoformat()
                    if version.published_at
                    else None,
                }
            )
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "metric_definition_version": "visitor-demo-1",
        "scope": {
            "workspace_id": wid,
            "source_id": source_id,
            "file_format": file_format,
            "asset_status": asset_status,
        },
        "raw": {
            "source_count": len(sources),
            "asset_count": len(assets),
            "physical_file_count": physical_files,
            "unique_content_count": unique_content,
            "total_bytes": total_bytes,
            "authorization": grant_status,
        },
        "formats": format_distribution,
        "format_stats": format_stats,
        "business_types": business_distribution,
        "parsing": {
            "document_count": len(documents),
            "document_version_count": len(versions),
            "segment_count": segment_count,
            "parse_status": {
                key: sum(1 for row in documents if row.parse_status == key)
                for key in {row.parse_status for row in documents}
            },
            "run_status": run_status,
            "failure_reasons": failure_reasons,
        },
        "quality": {
            "issue_status": issue_status,
            "issue_count": len(issues),
            "candidate_status": candidate_status,
            "candidate_count": len(candidates),
        },
        "products": product_summary,
        "recent_versions": recent_versions,
        "funnel": [
            {"stage": "assets", "count": len(assets), "unit": "asset"},
            {
                "stage": "parsed_documents",
                "count": len([row for row in documents if row.parse_status == "succeeded"]),
                "unit": "document",
            },
            {"stage": "segments", "count": segment_count, "unit": "segment"},
            {
                "stage": "approved_candidates",
                "count": candidate_status.get("approved", 0),
                "unit": "candidate_sample",
            },
            {
                "stage": "published_versions",
                "count": sum(item["published"] for item in product_summary.values()),
                "unit": "dataset_version",
            },
        ],
    }


@router.get("/assets/{asset_id}/lineage-view")
def asset_lineage_view(
    asset_id: str,
    request: Request,
    session: Session = Depends(db),
    document_version_id: str | None = None,
):
    """Return one asset's signed source and persisted parser representations."""
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    asset = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == wid))
    if not asset:
        raise HTTPException(404, "NOT_FOUND")
    blob = session.scalar(
        select(AssetBlob).where(AssetBlob.id == asset.blob_id, AssetBlob.workspace_id == wid)
    )
    source = session.scalar(
        select(Source).where(Source.id == asset.source_id, Source.workspace_id == wid)
    )
    document = session.scalar(
        select(Document).where(Document.asset_id == asset.id, Document.workspace_id == wid)
    )
    versions = (
        list(
            session.scalars(
                select(DocumentVersion)
                .where(
                    DocumentVersion.workspace_id == wid, DocumentVersion.document_id == document.id
                )
                .order_by(DocumentVersion.version_no.desc())
            ).all()
        )
        if document
        else []
    )
    selected = next(
        (row for row in versions if row.id == document_version_id),
        versions[0] if versions else None,
    )

    original: dict[str, Any] = {"status": "NOT_AVAILABLE", "url": None, "expires_in": 0}
    if blob:
        try:
            from corpusflow.adapters.storage import S3ObjectStore

            store = S3ObjectStore(
                request.app.state.config.object_store_endpoint,
                request.app.state.config.object_store_bucket,
                request.app.state.config.object_store_access_key.get_secret_value(),
                request.app.state.config.object_store_secret_key.get_secret_value(),
            )
            original = {
                "status": "AVAILABLE",
                "url": store.presign_get(blob.storage_key, 300),
                "expires_in": 300,
            }
        except Exception:
            original = {"status": "NOT_AVAILABLE", "url": None, "expires_in": 0}

    def representation(version: DocumentVersion | None) -> dict[str, Any] | None:
        if not version:
            return None
        segments = list(
            session.scalars(
                select(Segment)
                .where(Segment.document_version_id == version.id, Segment.workspace_id == wid)
                .order_by(Segment.created_at)
            ).all()
        )
        artifacts = (
            list(
                session.scalars(
                    select(Artifact)
                    .where(Artifact.workspace_id == wid, Artifact.run_id == version.run_id)
                    .order_by(Artifact.created_at.desc())
                ).all()
            )
            if version.run_id
            else []
        )
        markdown_artifact = next(
            (row for row in artifacts if row.kind.startswith("document_markdown")), None
        )
        json_artifact = next(
            (row for row in artifacts if row.kind.startswith("document_json")), None
        )

        def read_artifact(row: Artifact | None, content_type: str) -> dict[str, Any]:
            if not row:
                return {"status": "NOT_AVAILABLE", "content": None}
            try:
                from corpusflow.adapters.storage import S3ObjectStore

                store = S3ObjectStore(
                    request.app.state.config.object_store_endpoint,
                    request.app.state.config.object_store_bucket,
                    request.app.state.config.object_store_access_key.get_secret_value(),
                    request.app.state.config.object_store_secret_key.get_secret_value(),
                )
                content = store.get(row.storage_key)
                if len(content) > 2_000_000:
                    return {
                        "status": "TRUNCATED",
                        "content": content[:2_000_000].decode("utf-8", "replace"),
                        "sha256": row.content_sha256,
                        "artifact_id": row.id,
                        "content_type": content_type,
                    }
                return {
                    "status": "AVAILABLE",
                    "content": content.decode("utf-8", "replace"),
                    "sha256": row.content_sha256,
                    "artifact_id": row.id,
                    "content_type": content_type,
                }
            except Exception:
                return {
                    "status": "NOT_AVAILABLE",
                    "content": None,
                    "sha256": row.content_sha256,
                    "artifact_id": row.id,
                    "content_type": content_type,
                }

        structured = read_artifact(json_artifact, "application/json")
        structured_data: Any = None
        if structured.get("content"):
            try:
                structured_data = json.loads(structured["content"])
            except json.JSONDecodeError:
                structured_data = None
        if structured_data is None:
            structured_data = {
                "document_version_id": version.id,
                "version_no": version.version_no,
                "parser": {
                    "name": version.parser_name,
                    "version": version.parser_version,
                    "config_hash": version.config_hash,
                },
                "segments": [
                    {
                        "segment_id": row.id,
                        "title": row.section_title,
                        "text": row.text,
                        "location": row.location_json,
                        "token_count": row.token_count,
                        "quality_state": row.quality_state,
                    }
                    for row in segments
                ],
            }
            structured["status"] = "DATABASE_VIEW"
        return {
            "document_version_id": version.id,
            "version_no": version.version_no,
            "parser_name": version.parser_name,
            "parser_version": version.parser_version,
            "config_hash": version.config_hash,
            "run_id": version.run_id,
            "status": version.status,
            "markdown": read_artifact(markdown_artifact, "text/markdown"),
            "structured": {**structured, "data": structured_data},
            "segments": [
                {
                    "segment_id": row.id,
                    "title": row.section_title,
                    "text": row.text,
                    "location": row.location_json,
                    "token_count": row.token_count,
                    "quality_state": row.quality_state,
                    "content_hash": row.content_hash,
                }
                for row in segments
            ],
        }

    return {
        "asset": {
            "asset_id": asset.id,
            "filename": asset.filename,
            "format": asset.format,
            "source_id": asset.source_id,
            "source_name": source.name if source else None,
            "sha256": blob.sha256 if blob else None,
            "byte_size": blob.byte_size if blob else None,
            "media_type": blob.media_type if blob else None,
            "metadata": asset.metadata_json,
        },
        "original": original,
        "document": {
            "document_id": document.id,
            "title": document.title,
            "parse_status": document.parse_status,
        }
        if document
        else None,
        "selected_version_id": selected.id if selected else None,
        "versions": [representation(row) for row in versions],
    }


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == wid))
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    blob = session.scalar(select(AssetBlob).where(AssetBlob.id == row.blob_id))
    source = session.scalar(
        select(Source).where(Source.id == row.source_id, Source.workspace_id == wid)
    )
    document = session.scalar(
        select(Document).where(Document.asset_id == row.id, Document.workspace_id == wid)
    )
    versions = (
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id, DocumentVersion.workspace_id == wid)
            .order_by(DocumentVersion.version_no.desc())
        ).all()
        if document
        else []
    )
    return {
        "asset_id": row.id,
        "filename": row.filename,
        "format": row.format,
        "source": {"source_id": source.id, "name": source.name, "kind": source.kind}
        if source
        else None,
        "blob": {
            "storage_key": blob.storage_key,
            "sha256": blob.sha256,
            "byte_size": blob.byte_size,
            "media_type": blob.media_type,
        }
        if blob
        else None,
        "ingestion_status": row.ingestion_status,
        "quality_status": row.quality_status,
        "language": row.language,
        "metadata": row.metadata_json,
        "document": {
            "document_id": document.id,
            "title": document.title,
            "parse_status": document.parse_status,
        }
        if document
        else None,
        "versions": [
            {
                "document_version_id": version.id,
                "version_no": version.version_no,
                "content_sha256": version.content_sha256,
                "parser_name": version.parser_name,
                "parser_version": version.parser_version,
                "config_hash": version.config_hash,
                "run_id": version.run_id,
                "status": version.status,
                "segments": [
                    {
                        "segment_id": segment.id,
                        "source_id": segment.source_id,
                        "content_hash": segment.content_hash,
                        "text": segment.text,
                        "quality_state": segment.quality_state,
                        "location": segment.location_json,
                        "token_count": segment.token_count,
                        "section_title": segment.section_title,
                    }
                    for segment in session.scalars(
                        select(Segment)
                        .where(
                            Segment.document_version_id == version.id,
                            Segment.workspace_id == wid,
                        )
                        .order_by(Segment.created_at)
                    ).all()
                ],
            }
            for version in versions
        ],
    }


class MetadataProposalUpdate(BaseModel):
    fields: dict[str, Any]


def _proposal_payload(row: MetadataProposal) -> dict[str, Any]:
    return {
        "proposal_id": row.id,
        "asset_id": row.asset_id,
        "status": row.status,
        "revision": row.revision,
        "parser": {"name": row.parser_name, "version": row.parser_version},
        "fields": row.fields,
        "field_sources": row.field_sources,
        "confidence": row.confidence,
        "error": row.error,
        "confirmed_by": row.confirmed_by,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
    }


@router.get("/assets/{asset_id}/metadata-proposals")
def metadata_proposals(asset_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    asset = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == wid))
    if not asset:
        raise HTTPException(404, "NOT_FOUND")
    rows = session.scalars(
        select(MetadataProposal)
        .where(MetadataProposal.asset_id == asset_id, MetadataProposal.workspace_id == wid)
        .order_by(MetadataProposal.created_at.desc())
    ).all()
    confirmed = session.scalar(
        select(DocumentMetadata).where(
            DocumentMetadata.asset_id == asset_id, DocumentMetadata.workspace_id == wid
        )
    )
    return {
        "items": [_proposal_payload(row) for row in rows],
        "confirmed": {
            "title": confirmed.title,
            "document_type": confirmed.document_type,
            "authors": confirmed.authors,
            "abstract": confirmed.abstract,
            "keywords": confirmed.keywords,
            "research_field": confirmed.research_field,
            "journal": confirmed.journal,
            "conference": confirmed.conference,
            "publication_year": confirmed.publication_year,
            "doi": confirmed.doi,
            "language": confirmed.language,
            "source_url": confirmed.source_url,
            "license_text": confirmed.license_text,
        }
        if confirmed
        else None,
    }


@router.patch("/assets/{asset_id}/metadata-proposals/{proposal_id}")
def update_metadata_proposal(
    asset_id: str,
    proposal_id: str,
    body: MetadataProposalUpdate,
    request: Request,
    session: Session = Depends(db),
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    row = session.scalar(
        select(MetadataProposal).where(
            MetadataProposal.id == proposal_id,
            MetadataProposal.asset_id == asset_id,
            MetadataProposal.workspace_id == wid,
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    if row.status == "confirmed":
        raise HTTPException(409, "METADATA_ALREADY_CONFIRMED")
    row.fields = body.fields
    row.status = "edited"
    audit(session, request, wid, user, "metadata.proposal.update", "asset", asset_id)
    session.commit()
    return _proposal_payload(row)


@router.post("/assets/{asset_id}/metadata-proposals/{proposal_id}/confirm")
def confirm_metadata_proposal(
    asset_id: str, proposal_id: str, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer", "reviewer"})
    row = session.scalar(
        select(MetadataProposal).where(
            MetadataProposal.id == proposal_id,
            MetadataProposal.asset_id == asset_id,
            MetadataProposal.workspace_id == wid,
        )
    )
    asset = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == wid))
    if not row or not asset:
        raise HTTPException(404, "NOT_FOUND")
    if row.status == "confirmed":
        return _proposal_payload(row)
    fields = row.fields if isinstance(row.fields, dict) else {}
    metadata = session.scalar(
        select(DocumentMetadata).where(
            DocumentMetadata.asset_id == asset_id, DocumentMetadata.workspace_id == wid
        )
    )
    if not metadata:
        metadata = DocumentMetadata(workspace_id=wid, asset_id=asset_id, confirmed_by=user)
        session.add(metadata)
    for key in (
        "document_type",
        "title",
        "authors",
        "abstract",
        "keywords",
        "research_field",
        "journal",
        "conference",
        "publication_year",
        "doi",
        "language",
        "source_url",
        "license_text",
    ):
        if key in fields:
            setattr(metadata, key, fields[key])
    metadata.confirmed_by = user
    asset.metadata_json = {**(asset.metadata_json or {}), **fields, "status": "confirmed"}
    asset.language = fields.get("language") or asset.language
    asset.ingestion_status = "registered"
    row.status = "confirmed"
    row.confirmed_by = user
    row.confirmed_at = datetime.now(timezone.utc)
    audit(
        session,
        request,
        wid,
        user,
        "metadata.proposal.confirm",
        "asset",
        asset_id,
        {"proposal_id": proposal_id},
    )
    session.commit()
    return _proposal_payload(row)


@router.post("/assets/{asset_id}/metadata-proposals/{proposal_id}/retry")
def retry_metadata_proposal(
    asset_id: str, proposal_id: str, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    row = session.scalar(
        select(MetadataProposal).where(
            MetadataProposal.id == proposal_id,
            MetadataProposal.asset_id == asset_id,
            MetadataProposal.workspace_id == wid,
        )
    )
    asset = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == wid))
    blob = (
        session.scalar(
            select(AssetBlob).where(AssetBlob.id == asset.blob_id, AssetBlob.workspace_id == wid)
        )
        if asset
        else None
    )
    if not row or not asset or not blob:
        raise HTTPException(404, "NOT_FOUND")
    try:
        from corpusflow.adapters.storage import S3ObjectStore

        store = S3ObjectStore(
            request.app.state.config.object_store_endpoint,
            request.app.state.config.object_store_bucket,
            request.app.state.config.object_store_access_key.get_secret_value(),
            request.app.state.config.object_store_secret_key.get_secret_value(),
        )
        content = store.get(blob.storage_key)
    except Exception as exc:
        row.status, row.error = "failed", f"OBJECT_READ_FAILED: {exc.__class__.__name__}"
        session.commit()
        return _proposal_payload(row)
    fields, sources, confidence = extract_metadata(asset.filename, blob.media_type, content)
    row.status, row.error, row.fields, row.field_sources, row.confidence = (
        "pending",
        None,
        fields,
        sources,
        confidence,
    )
    audit(session, request, wid, user, "metadata.proposal.retry", "asset", asset_id)
    session.commit()
    return _proposal_payload(row)


class PipelineIn(BaseModel):
    asset_ids: list[str] = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)


def ensure_pipeline(session: Session, wid: str) -> PipelineVersion:
    template = session.scalar(select(PipelineTemplate).where(PipelineTemplate.workspace_id == wid))
    if not template:
        template = PipelineTemplate(
            workspace_id=wid, name="builtin-document", template_type="document"
        )
        session.add(template)
        session.flush()
    version = session.scalar(
        select(PipelineVersion).where(
            PipelineVersion.template_id == template.id, PipelineVersion.semver == "1.1.0"
        )
    )
    if not version:
        dag = {
            "nodes": [
                {"id": "parse", "operator": "builtin.parser"},
                {"id": "clean", "operator": "builtin.clean", "config": {}},
                {"id": "deduplicate", "operator": "builtin.deduplicate", "config": {}},
                {"id": "quality", "operator": "builtin.quality", "config": {}},
            ],
            "edges": [["parse", "clean"], ["clean", "deduplicate"], ["deduplicate", "quality"]],
        }
        version = PipelineVersion(
            template_id=template.id, semver="1.1.0", dag_json=dag, dag_hash=digest(dag)
        )
        session.add(version)
        session.flush()
    definitions = [
        (
            "builtin.clean",
            "1.0.0",
            {"text": "string"},
            {"text": "string"},
            {"collapse_whitespace": "boolean"},
        ),
        (
            "builtin.deduplicate",
            "1.0.0",
            {"text": "string"},
            {"text": "string"},
            {"lowercase": "boolean"},
        ),
        (
            "builtin.quality",
            "1.0.0",
            {"text": "string"},
            {"metrics": "object"},
            {"min_chars": "integer"},
        ),
    ]
    for key, operator_version, input_schema, output_schema, params_schema in definitions:
        if not session.scalar(
            select(OperatorDefinition).where(
                OperatorDefinition.operator_key == key,
                OperatorDefinition.version == operator_version,
            )
        ):
            session.add(
                OperatorDefinition(
                    operator_key=key,
                    version=operator_version,
                    adapter_kind="builtin",
                    input_schema=input_schema,
                    output_schema=output_schema,
                    params_schema=params_schema,
                )
            )
    return version


def pipeline_batch_response(session: Session, batch: ProcessingBatch) -> dict[str, Any]:
    runs = session.scalars(
        select(PipelineRun).where(PipelineRun.batch_id == batch.id).order_by(PipelineRun.created_at)
    ).all()
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "accepted": [{"run_id": run.id, "asset_id": run.asset_id} for run in runs],
        "rejected": [],
        "idempotent": True,
    }


@router.post("/pipeline-runs/batches")
def pipeline_batch(
    body: PipelineIn,
    request: Request,
    session: Session = Depends(db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    request_hash = digest({"asset_ids": body.asset_ids, "config": body.config})
    if idempotency_key:
        existing = session.scalar(
            select(ProcessingBatch).where(
                ProcessingBatch.workspace_id == wid,
                ProcessingBatch.idempotency_key == idempotency_key,
            )
        )
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
            return pipeline_batch_response(session, existing)
    version = ensure_pipeline(session, wid)
    batch = ProcessingBatch(
        workspace_id=wid,
        created_by=user,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    session.add(batch)
    session.flush()
    accepted = []
    rejected = []
    for aid in body.asset_ids:
        asset = session.scalar(select(Asset).where(Asset.id == aid, Asset.workspace_id == wid))
        if not asset:
            rejected.append({"asset_id": aid, "reason": "NOT_FOUND"})
            continue
        run = PipelineRun(
            workspace_id=wid,
            batch_id=batch.id,
            asset_id=aid,
            pipeline_version_id=version.id,
            config_snapshot=body.config,
            snapshot_hash=digest(body.config),
        )
        session.add(run)
        session.flush()
        session.add(NodeRun(run_id=run.id, node_id="parse", status="pending"))
        session.flush()
        enqueue_run(session, wid, run.id)
        accepted.append({"run_id": run.id, "asset_id": aid})
    batch.status = "queued" if accepted else "failed"
    audit(session, request, wid, user, "pipeline.batch.create", "processing_batch", batch.id)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if idempotency_key:
            existing = session.scalar(
                select(ProcessingBatch).where(
                    ProcessingBatch.workspace_id == wid,
                    ProcessingBatch.idempotency_key == idempotency_key,
                )
            )
            if existing and existing.request_hash == request_hash:
                return pipeline_batch_response(session, existing)
        raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED") from exc
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "accepted": accepted,
        "rejected": rejected,
        "idempotent": False,
    }


@router.get("/pipeline-runs/{run_id}")
def get_run(run_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    run = session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == wid)
    )
    if not run:
        raise HTTPException(404, "NOT_FOUND")
    pipeline = session.get(PipelineVersion, run.pipeline_version_id)
    return {
        "run_id": run.id,
        "asset_id": run.asset_id,
        "status": run.status,
        "snapshot_hash": run.snapshot_hash,
        "error_code": run.error_code,
        "revision": run.revision,
        "dag": pipeline.dag_json if pipeline else None,
        "nodes": [
            {
                "node_id": node.node_id,
                "status": node.status,
                "attempt": node.attempt_no,
                "operator_key": node.operator_key,
                "operator_version": node.operator_version,
                "input_count": node.input_count,
                "output_count": node.output_count,
                "filtered_count": node.filtered_count,
                "duration_ms": node.duration_ms,
                "failure_code": node.failure_code,
                "config": node.config_snapshot,
                "log_ref": node.log_ref,
            }
            for node in session.scalars(
                select(NodeRun).where(NodeRun.run_id == run.id).order_by(NodeRun.created_at)
            ).all()
        ],
    }


@router.get("/pipeline-runs/{run_id}/artifacts")
def run_artifacts(run_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    if not session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == wid)
    ):
        raise HTTPException(404, "NOT_FOUND")
    return {
        "items": [
            {
                "artifact_id": artifact.id,
                "kind": artifact.kind,
                "storage_key": artifact.storage_key,
                "sha256": artifact.content_sha256,
                "immutable": artifact.immutable,
            }
            for artifact in session.scalars(
                select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)
            ).all()
        ]
    }


@router.get("/processing/operators")
def processing_operators(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    del user
    builtins = session.scalars(
        select(OperatorDefinition).where(OperatorDefinition.adapter_kind == "builtin")
    ).all()
    if not builtins:
        ensure_pipeline(session, wid)
        session.flush()
        builtins = session.scalars(
            select(OperatorDefinition).where(OperatorDefinition.adapter_kind == "builtin")
        ).all()
    return {
        "items": [
            {
                "operator_key": operator.operator_key,
                "version": operator.version,
                "adapter_kind": operator.adapter_kind,
                "params_schema": operator.params_schema,
                "available": True,
            }
            for operator in builtins
        ]
        + [
            {
                "operator_key": "data-juicer",
                "version": "unconfigured",
                "adapter_kind": "external",
                "params_schema": {},
                "available": False,
                "reason": "外部可执行文件未配置",
            },
            {
                "operator_key": "weknora.docreader",
                "version": "unconfigured",
                "adapter_kind": "external",
                "params_schema": {},
                "available": False,
                "reason": "docreader gRPC endpoint 未配置",
            },
        ],
    }


@router.post("/pipeline-runs/{run_id}/execute", status_code=202)
def execute_run(run_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    run = session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == wid)
    )
    if not run:
        raise HTTPException(404, "NOT_FOUND")
    if run.status in {"awaiting_review", "rejected", "isolated"}:
        raise HTTPException(409, "RUN_REVIEW_BLOCKED")
    run.status = "queued"
    enqueue_run(session, wid, run.id)
    audit(session, request, wid, user, "pipeline.run.enqueue", "pipeline_run", run.id)
    session.commit()
    return {"run_id": run.id, "status": run.status, "queued": True}


class IssueReviewIn(BaseModel):
    decision: str = Field(pattern="^(approved_for_rework|rejected|returned|isolated)$")
    note: str = ""


class IssueIn(BaseModel):
    run_id: str | None = None
    asset_id: str | None = None
    reason: str = Field(min_length=1)
    severity: str = "medium"


@router.get("/quality/issues")
def quality_issues(
    request: Request,
    session: Session = Depends(db),
    status: str | None = None,
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    query = select(QualityIssue).where(QualityIssue.workspace_id == wid)
    if status:
        query = query.where(QualityIssue.status == status)
    rows = session.scalars(query.order_by(QualityIssue.created_at.desc()).limit(200)).all()
    return {
        "items": [
            {
                "issue_id": row.id,
                "run_id": row.run_id,
                "asset_id": row.asset_id,
                "status": row.status,
                "severity": row.severity,
                "reason": row.reason,
                "rule_version": row.rule_version,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/quality/issues")
def create_issue(body: IssueIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    issue = QualityIssue(
        workspace_id=wid,
        run_id=body.run_id,
        asset_id=body.asset_id,
        reason=body.reason,
        severity=body.severity,
    )
    session.add(issue)
    session.flush()
    if body.run_id:
        run = session.scalar(
            select(PipelineRun).where(
                PipelineRun.id == body.run_id, PipelineRun.workspace_id == wid
            )
        )
        if run:
            run.status = "awaiting_review"
    audit(session, request, wid, user, "quality.issue.create", "quality_issue", issue.id)
    session.commit()
    return {"issue_id": issue.id, "status": issue.status}


@router.post("/quality/issues/{issue_id}/reviews")
def review_issue(
    issue_id: str, body: IssueReviewIn, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "reviewer"})
    issue = session.scalar(
        select(QualityIssue).where(QualityIssue.id == issue_id, QualityIssue.workspace_id == wid)
    )
    if not issue:
        raise HTTPException(404, "NOT_FOUND")
    if issue.status in {"rejected", "isolated", "resolved"}:
        raise HTTPException(409, "INVALID_STATE_TRANSITION")
    issue.status = body.decision
    session.add(
        QualityReview(issue_id=issue.id, reviewer_id=user, decision=body.decision, note=body.note)
    )
    audit(
        session,
        request,
        wid,
        user,
        "quality.issue.review",
        "quality_issue",
        issue.id,
        {"decision": body.decision},
    )
    session.commit()
    return {"issue_id": issue.id, "status": issue.status}


class QualityEvaluationIn(BaseModel):
    target_type: str = Field(pattern="^(dataset_build|dataset_version)$")
    target_id: str
    rule_version_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


@router.get("/quality/rules")
def quality_rules(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rule_set, version = default_rule_set(session, wid, user)
    versions = list(
        session.scalars(
            select(QualityRuleVersion)
            .where(QualityRuleVersion.rule_set_id == rule_set.id)
            .order_by(QualityRuleVersion.created_at.desc())
        )
    )
    session.commit()
    return {
        "metric_catalog": {
            key: {"method": value[0], "direction": value[1], "default_threshold": value[2]}
            for key, value in METRICS.items()
        },
        "rule_set": {
            "id": rule_set.id,
            "name": rule_set.name,
            "product_type": rule_set.product_type,
        },
        "versions": [
            {
                "id": version.id,
                "version": version.version,
                "config_hash": version.config_hash,
                "rules": version.rules_json,
                "status": version.status,
            }
            for version in versions
        ],
    }


class QualityRuleConfigIn(BaseModel):
    enabled: bool = True
    threshold: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    manual_review: bool = False


class QualityRuleVersionIn(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=50)
    rules: dict[str, QualityRuleConfigIn]


@router.post("/quality/rules/versions")
def create_quality_rule_version(
    body: QualityRuleVersionIn, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin"})
    rule_set, latest = default_rule_set(session, wid, user)
    if not body.rules or any(key not in METRICS for key in body.rules):
        raise HTTPException(422, "INVALID_QUALITY_RULE")
    rules = {**latest.rules_json, **{key: value.model_dump() for key, value in body.rules.items()}}
    for key, config in rules.items():
        if (
            key != "sample.token_count"
            and config["threshold"] is not None
            and config["threshold"] > 1
        ):
            raise HTTPException(422, "INVALID_QUALITY_RULE")
    existing = session.scalar(
        select(QualityRuleVersion).where(
            QualityRuleVersion.rule_set_id == rule_set.id,
            QualityRuleVersion.version == body.version,
        )
    )
    if existing:
        if existing.config_hash != digest(rules):
            raise HTTPException(409, "VERSION_CONFLICT")
        return {"id": existing.id, "version": existing.version, "config_hash": existing.config_hash}
    row = QualityRuleVersion(
        rule_set_id=rule_set.id,
        version=body.version,
        rules_json=rules,
        config_hash=digest(rules),
        created_by=user,
    )
    session.add(row)
    session.flush()
    audit(
        session,
        request,
        wid,
        user,
        "quality.rules.version",
        "quality_rule_version",
        row.id,
        {"version": row.version, "config_hash": row.config_hash},
    )
    session.commit()
    return {"id": row.id, "version": row.version, "config_hash": row.config_hash}


@router.post("/quality/evaluations")
def create_quality_evaluation(
    body: QualityEvaluationIn, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer", "reviewer"})
    try:
        run, report = evaluate_quality(
            session,
            wid,
            user,
            body.target_type,
            body.target_id,
            rule_version_id=body.rule_version_id,
            idempotency_key=body.idempotency_key,
            settings=request.app.state.config,
        )
    except ValueError as exc:
        raise HTTPException(404 if str(exc) == "NOT_FOUND" else 409, str(exc)) from exc
    audit(
        session,
        request,
        wid,
        user,
        "quality.evaluation.create",
        "quality_evaluation_run",
        run.id,
        {"target_type": body.target_type, "target_id": body.target_id},
    )
    session.commit()
    return {
        "evaluation_id": run.id,
        "status": run.status,
        "target_type": run.target_type,
        "target_id": run.target_id,
        "report": report,
    }


@router.get("/quality/evaluations")
def list_quality_evaluations(
    request: Request, session: Session = Depends(db), limit: int = Query(default=50, ge=1, le=200)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = session.scalars(
        select(QualityEvaluationRun)
        .where(QualityEvaluationRun.workspace_id == wid)
        .order_by(QualityEvaluationRun.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "items": [
            {
                "evaluation_id": row.id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "status": row.status,
                "quality_status": row.config_snapshot.get("report", {}).get(
                    "quality_status", "NOT_EVALUATED"
                ),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/quality/evaluations/{evaluation_id}")
def quality_evaluation(evaluation_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    run = session.scalar(
        select(QualityEvaluationRun).where(
            QualityEvaluationRun.id == evaluation_id, QualityEvaluationRun.workspace_id == wid
        )
    )
    if not run:
        raise HTTPException(404, "NOT_FOUND")
    audit(session, request, wid, user, "quality.report.read", "quality_evaluation_run", run.id)
    session.commit()
    metrics = session.scalars(
        select(QualityMetricResult).where(QualityMetricResult.evaluation_run_id == run.id)
    ).all()
    return {
        "evaluation_id": run.id,
        "status": run.status,
        "target_type": run.target_type,
        "target_id": run.target_id,
        "rule_version_id": run.rule_version_id,
        "report": run.config_snapshot.get("report"),
        "metrics": [
            {
                "metric_id": m.metric_id,
                "value": m.value_numeric,
                "numerator": m.numerator,
                "denominator": m.denominator,
                "unit": m.unit,
                "status": m.status,
                "threshold": m.threshold_json,
                "scope": m.scope_json,
                "evidence": m.evidence_json,
            }
            for m in metrics
        ],
    }


@router.get("/quality/reports/{dataset_version_id}")
def quality_report(dataset_version_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    report = session.scalar(
        select(DatasetQualityReport)
        .where(
            DatasetQualityReport.dataset_version_id == dataset_version_id,
            DatasetQualityReport.workspace_id == wid,
        )
        .order_by(DatasetQualityReport.created_at.desc())
    )
    if not report:
        raise HTTPException(404, "NOT_FOUND")
    return {
        "report_id": report.id,
        "dataset_version_id": report.dataset_version_id,
        "evaluation_id": report.evaluation_run_id,
        "sha256": report.report_sha256,
        "immutable": report.immutable,
        "report": report.report_json,
    }


@router.get("/quality/coverage")
def quality_coverage_endpoint(
    request: Request,
    session: Session = Depends(db),
    dataset_version_id: str | None = None,
    source_id: str | None = None,
    product_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    try:
        return quality_coverage(
            session, wid, dataset_version_id, source_id, product_type, since, until
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/quality/ratios/{dataset_version_id}")
def quality_ratios_endpoint(
    dataset_version_id: str, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    try:
        return quality_ratios(session, wid, dataset_version_id)
    except ValueError as exc:
        raise HTTPException(404 if str(exc) == "NOT_FOUND" else 409, str(exc)) from exc


class VersionComparisonIn(BaseModel):
    left_version_id: str
    right_version_id: str


@router.post("/quality/version-comparisons")
def create_version_comparison(
    body: VersionComparisonIn, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer", "reviewer"})
    try:
        row = compare_quality_versions(
            session,
            wid,
            user,
            body.left_version_id,
            body.right_version_id,
            settings=request.app.state.config,
        )
    except ValueError as exc:
        code = "NOT_FOUND" if str(exc) == "NOT_FOUND" else str(exc)
        raise HTTPException(404 if code == "NOT_FOUND" else 409, code) from exc
    audit(
        session,
        request,
        wid,
        user,
        "quality.version.compare",
        "dataset_version_comparison",
        row.id,
        {"left": body.left_version_id, "right": body.right_version_id},
    )
    session.commit()
    return {"comparison_id": row.id, "status": row.status, "comparison": row.comparison_json}


@router.get("/quality/version-comparisons/{comparison_id}")
def version_comparison(comparison_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(DatasetVersionComparison).where(
            DatasetVersionComparison.id == comparison_id,
            DatasetVersionComparison.workspace_id == wid,
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    return {"comparison_id": row.id, "status": row.status, "comparison": row.comparison_json}


@router.post("/pipeline-runs/{run_id}/resume")
def resume_run(run_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    run = session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == wid)
    )
    if not run:
        raise HTTPException(404, "NOT_FOUND")
    issues = session.scalars(select(QualityIssue).where(QualityIssue.run_id == run.id)).all()
    if any(i.status in {"open", "in_review", "rejected", "isolated", "returned"} for i in issues):
        raise HTTPException(409, "RUN_REVIEW_BLOCKED")
    prepare_rework(session, run)
    run.status = "queued"
    run.revision += 1
    enqueue_run(session, wid, run.id)
    session.commit()
    return {"run_id": run.id, "status": run.status, "queued": True}


@router.get("/pipeline-runs/{run_id}/logs")
def run_logs(run_id: str, request: Request, session: Session = Depends(db)):
    from corpusflow.db.models import ExecutionLog

    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    if not session.scalar(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.workspace_id == wid)
    ):
        raise HTTPException(404, "NOT_FOUND")
    rows = session.scalars(
        select(ExecutionLog).where(ExecutionLog.run_id == run_id).order_by(ExecutionLog.created_at)
    ).all()
    return {
        "items": [
            {
                "level": r.level,
                "message": r.message,
                "attempt": r.attempt_no,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/documents/{document_id}/versions")
def document_versions(document_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.workspace_id == wid,
        )
    ).all()
    return {
        "items": [
            {
                "document_version_id": row.id,
                "version_no": row.version_no,
                "content_sha256": row.content_sha256,
                "parser_name": row.parser_name,
                "parser_version": row.parser_version,
                "config_hash": row.config_hash,
                "status": row.status,
                "segments": [
                    {
                        "segment_id": segment.id,
                        "source_id": segment.source_id,
                        "document_version_id": segment.document_version_id,
                        "content_hash": segment.content_hash,
                        "text": segment.text,
                        "quality_state": segment.quality_state,
                        "location": segment.location_json,
                        "token_count": segment.token_count,
                        "section_title": segment.section_title,
                    }
                    for segment in session.scalars(
                        select(Segment)
                        .where(Segment.document_version_id == row.id, Segment.workspace_id == wid)
                        .order_by(Segment.created_at)
                    ).all()
                ],
            }
            for row in rows
        ]
    }


@router.get("/segments/{segment_id}")
def segment_detail(segment_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(Segment).where(Segment.id == segment_id, Segment.workspace_id == wid)
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    return {
        "segment_id": row.id,
        "document_version_id": row.document_version_id,
        "source_id": row.source_id,
        "content_hash": row.content_hash,
        "text": row.text,
    }


@router.get("/datasets")
def datasets(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = session.scalars(
        select(Dataset).where(Dataset.workspace_id == wid).order_by(Dataset.created_at.desc())
    ).all()
    items = []
    for row in rows:
        versions = session.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == row.id)
            .order_by(DatasetVersion.created_at.desc())
        ).all()
        items.append(
            {
                "dataset_id": row.id,
                "name": row.name,
                "product_type": row.product_type,
                "created_at": row.created_at.isoformat(),
                "version_count": len(versions),
                "latest_version": versions[0].version if versions else None,
                "sample_count": sum(int(version.sample_count or 0) for version in versions),
            }
        )
    return {"items": items}


@router.get("/datasets/{dataset_id}/samples")
def dataset_samples(
    dataset_id: str,
    request: Request,
    session: Session = Depends(db),
    version: str | None = None,
    query: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    dataset = session.scalar(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.workspace_id == wid)
    )
    if not dataset:
        raise HTTPException(404, "NOT_FOUND")
    q = (
        select(CandidateSample, DatasetVersionSample, DatasetVersion)
        .join(DatasetVersionSample, DatasetVersionSample.candidate_sample_id == CandidateSample.id)
        .join(DatasetVersion, DatasetVersion.id == DatasetVersionSample.dataset_version_id)
        .where(CandidateSample.workspace_id == wid, DatasetVersion.dataset_id == dataset_id)
    )
    if version:
        q = q.where(DatasetVersion.version == version)
    rows = session.execute(
        q.order_by(CandidateSample.created_at, CandidateSample.id).offset(offset).limit(limit)
    ).all()
    total_q = (
        select(func.count())
        .select_from(CandidateSample)
        .join(DatasetVersionSample, DatasetVersionSample.candidate_sample_id == CandidateSample.id)
        .join(DatasetVersion, DatasetVersion.id == DatasetVersionSample.dataset_version_id)
        .where(CandidateSample.workspace_id == wid, DatasetVersion.dataset_id == dataset_id)
    )
    if version:
        total_q = total_q.where(DatasetVersion.version == version)
    result = []
    for sample, link, dv in rows:
        payload = sample.payload if isinstance(sample.payload, dict) else {}
        haystack = json.dumps(payload, ensure_ascii=False).lower()
        if query and query.lower() not in haystack:
            continue
        result.append(
            {
                "sample_id": sample.id,
                "sample_key": sample.sample_key,
                "status": sample.status,
                "payload": payload,
                "payload_hash": sample.payload_hash,
                "dataset_version_id": dv.id,
                "version": dv.version,
                "split": link.split,
                "source_id": sample.source_id,
                "created_at": sample.created_at.isoformat(),
            }
        )
    return {
        "items": result,
        "total_count": int(session.scalar(total_q) or 0),
        "dataset": {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "product_type": dataset.product_type,
        },
    }


class DatasetIn(BaseModel):
    name: str = Field(default="dataset", min_length=1, max_length=160)
    product_type: str = Field(default="sft", pattern="^(sft|pretrain|rag|evaluation|dpo)$")


@router.post("/datasets")
def create_dataset(body: DatasetIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    row = Dataset(
        workspace_id=wid,
        name=body.name,
        product_type=body.product_type,
    )
    session.add(row)
    session.commit()
    return {"dataset_id": row.id, "name": row.name, "product_type": row.product_type}


@router.get("/dataset-products/types")
def dataset_product_types(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    workspace_id(request, session, user)
    return {
        "items": [
            {
                "product_type": "sft",
                "purpose": "training",
                "schema_version": "sft.v1",
                "description": "对话消息格式的监督微调数据集",
            },
            {
                "product_type": "pretrain",
                "purpose": "training",
                "schema_version": "pretrain.v1",
                "description": "按来源组织的连续预训练语料",
            },
            {
                "product_type": "rag",
                "purpose": "rag",
                "schema_version": "rag.v1",
                "description": "带来源定位的知识片段数据集",
            },
            {
                "product_type": "evaluation",
                "purpose": "evaluation",
                "schema_version": "evaluation.v1",
                "description": "带证据关联的问答评测数据集",
            },
            {
                "product_type": "dpo",
                "purpose": "training",
                "schema_version": "dpo.v1",
                "description": "经人工成对偏好审核的 DPO 优化数据集",
            },
        ]
    }


class DpoImportSampleIn(BaseModel):
    sample_key: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=20000)
    response_a: str = Field(min_length=1, max_length=50000)
    response_b: str = Field(min_length=1, max_length=50000)
    source_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=50)
    prompt_messages: list[dict[str, Any]] | None = None
    candidate_model: str | None = Field(default=None, max_length=160)
    model_version: str | None = Field(default=None, max_length=160)
    generation_config: dict[str, Any] = Field(default_factory=dict)


class DpoImportIn(BaseModel):
    request_key: str = Field(min_length=1, max_length=120)
    samples: list[DpoImportSampleIn] = Field(min_length=1, max_length=100)


def _dpo_evidence_asset(
    session: Session, workspace: str, source_id: str, evidence_ids: list[str]
) -> Asset | None:
    segments = list(
        session.scalars(
            select(Segment).where(
                Segment.workspace_id == workspace,
                Segment.id.in_(evidence_ids),
            )
        ).all()
    )
    if len(segments) != len(set(evidence_ids)) or any(
        segment.source_id != source_id for segment in segments
    ):
        return None
    versions = {segment.document_version_id for segment in segments}
    if len(versions) != 1:
        return None
    return session.scalar(
        select(Asset)
        .join(Document, Document.asset_id == Asset.id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            Asset.workspace_id == workspace,
            Document.workspace_id == workspace,
            DocumentVersion.workspace_id == workspace,
            DocumentVersion.id == next(iter(versions)),
        )
    )


@router.get("/dpo/overview")
def dpo_overview(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = list(
        session.scalars(
            select(PreferenceSample)
            .where(PreferenceSample.workspace_id == wid)
            .order_by(PreferenceSample.created_at.desc())
            .limit(5000)
        )
    )
    statuses = {
        status: sum(row.status == status for row in rows)
        for status in {"pending", "annotated", "tie", "uncertain", "rejected", "approved"}
    }
    build_count = int(
        session.scalar(
            select(func.count())
            .select_from(DatasetBuild)
            .join(Dataset, Dataset.id == DatasetBuild.dataset_id)
            .where(DatasetBuild.workspace_id == wid, Dataset.product_type == "dpo")
        )
        or 0
    )
    published_count = int(
        session.scalar(
            select(func.count())
            .select_from(DatasetVersion)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                DatasetVersion.workspace_id == wid,
                Dataset.product_type == "dpo",
                DatasetVersion.status == "published",
            )
        )
        or 0
    )
    return {
        "workspace_id": wid,
        "total": len(rows),
        "statuses": statuses,
        "built_count": build_count,
        "published_count": published_count,
        "annotation_version": "dpo.preference.v1",
    }


@router.post("/dpo/preferences/import")
def import_dpo_preferences(body: DpoImportIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    keys = [item.sample_key for item in body.samples]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "INVALID_PREFERENCE")
    request_hash = digest([item.model_dump() for item in body.samples])
    existing = list(
        session.scalars(
            select(PreferenceSample).where(
                PreferenceSample.workspace_id == wid,
                PreferenceSample.import_request_key == body.request_key,
            )
        )
    )
    if existing:
        if len(existing) != len(keys) or any(
            row.import_request_hash != request_hash for row in existing
        ):
            raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
        return {
            "items": [
                {"preference_sample_id": row.id, "sample_key": row.sample_key} for row in existing
            ],
            "idempotent": True,
        }
    created: list[PreferenceSample] = []
    for item in body.samples:
        if item.response_a.strip() == item.response_b.strip():
            raise HTTPException(422, "INVALID_PREFERENCE")
        asset = _dpo_evidence_asset(session, wid, item.source_id, item.evidence_ids)
        if not asset or not current_grant(session, wid, asset.id, "training"):
            raise HTTPException(409, "PURPOSE_GRANT_MISSING")
        row = PreferenceSample(
            workspace_id=wid,
            sample_key=item.sample_key,
            import_request_key=body.request_key,
            import_request_hash=request_hash,
            prompt=item.prompt.strip(),
            prompt_messages=item.prompt_messages,
            response_a=item.response_a.strip(),
            response_b=item.response_b.strip(),
            source_id=item.source_id,
            evidence_ids=list(dict.fromkeys(item.evidence_ids)),
            candidate_model=item.candidate_model,
            model_version=item.model_version,
            generation_config=item.generation_config,
            imported_by=user,
            annotation_version="dpo.preference.v1",
        )
        session.add(row)
        session.flush()
        created.append(row)
        for evidence_id in row.evidence_ids:
            edge(session, wid, "Segment", evidence_id, "PreferenceSample", row.id, "supports")
    audit(
        session,
        request,
        wid,
        user,
        "dpo.preferences.import",
        "preference_sample",
        body.request_key,
        {"count": len(created), "source": "imported_fixture_or_review_record"},
    )
    session.commit()
    return {
        "items": [
            {"preference_sample_id": row.id, "sample_key": row.sample_key} for row in created
        ],
        "idempotent": False,
    }


@router.get("/dpo/preferences")
def list_dpo_preferences(
    request: Request,
    session: Session = Depends(db),
    status: str | None = None,
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    query = select(PreferenceSample).where(PreferenceSample.workspace_id == wid)
    if status:
        query = query.where(PreferenceSample.status == status)
    rows = session.scalars(query.order_by(PreferenceSample.created_at.desc()).limit(500)).all()
    return {
        "items": [
            {
                "preference_sample_id": row.id,
                "sample_key": row.sample_key,
                "prompt": row.prompt,
                "response_a": row.response_a,
                "response_b": row.response_b,
                "chosen_response": row.chosen_response,
                "rejected_response": row.rejected_response,
                "status": row.status,
                "preference_reason": row.preference_reason,
                "source_id": row.source_id,
                "evidence_ids": row.evidence_ids,
                "reviewed_by": row.reviewed_by,
                "published_version_id": row.published_version_id,
                "candidate_model": row.candidate_model,
                "model_version": row.model_version,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/dpo/preferences/{preference_id}")
def get_dpo_preference(preference_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(PreferenceSample).where(
            PreferenceSample.id == preference_id, PreferenceSample.workspace_id == wid
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    annotations = session.scalars(
        select(PreferenceAnnotation)
        .where(
            PreferenceAnnotation.preference_sample_id == row.id,
            PreferenceAnnotation.workspace_id == wid,
        )
        .order_by(PreferenceAnnotation.created_at)
    ).all()
    return {
        "preference_sample_id": row.id,
        "sample_key": row.sample_key,
        "prompt": row.prompt,
        "prompt_messages": row.prompt_messages,
        "response_a": row.response_a,
        "response_b": row.response_b,
        "chosen_response": row.chosen_response,
        "rejected_response": row.rejected_response,
        "status": row.status,
        "preference_reason": row.preference_reason,
        "source_id": row.source_id,
        "evidence_ids": row.evidence_ids,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "annotation_version": row.annotation_version,
        "published_version_id": row.published_version_id,
        "annotations": [
            {
                "annotation_id": item.id,
                "annotator_id": item.annotator_id,
                "choice": item.choice,
                "reason": item.reason,
                "annotation_version": item.annotation_version,
                "presented_order": item.presented_order,
            }
            for item in annotations
        ],
    }


class DpoAnnotationIn(BaseModel):
    choice: str = Field(pattern="^(a|b|tie|uncertain|both_invalid)$")
    reason: str = Field(min_length=8, max_length=2000)


@router.post("/dpo/preferences/{preference_id}/annotations")
def annotate_dpo_preference(
    preference_id: str,
    body: DpoAnnotationIn,
    request: Request,
    session: Session = Depends(db),
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "reviewer"})
    row = session.scalar(
        select(PreferenceSample).where(
            PreferenceSample.id == preference_id, PreferenceSample.workspace_id == wid
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    if row.published_version_id:
        raise HTTPException(409, "PREFERENCE_IMMUTABLE")
    if user == row.imported_by:
        raise HTTPException(409, "REVIEWER_SEPARATION_REQUIRED")
    if session.scalar(
        select(PreferenceAnnotation).where(
            PreferenceAnnotation.preference_sample_id == row.id,
            PreferenceAnnotation.annotator_id == user,
        )
    ):
        raise HTTPException(409, "ANNOTATION_ALREADY_SUBMITTED")
    annotations = list(
        session.scalars(
            select(PreferenceAnnotation).where(PreferenceAnnotation.preference_sample_id == row.id)
        )
    )
    semantic_order = (
        {"left": "a", "right": "b"}
        if int(digest(row.sample_key)[:2], 16) % 2
        else {"left": "b", "right": "a"}
    )
    session.add(
        PreferenceAnnotation(
            workspace_id=wid,
            preference_sample_id=row.id,
            annotator_id=user,
            choice=body.choice,
            reason=body.reason,
            annotation_version="dpo.preference.v1",
            presented_order=semantic_order,
        )
    )
    annotations.append(
        PreferenceAnnotation(choice=body.choice, annotator_id=user, reason=body.reason)
    )
    clear = {item.choice for item in annotations if item.choice in {"a", "b"}}
    if body.choice in {"tie", "uncertain", "both_invalid"}:
        row.status = body.choice
        row.chosen_response = None
        row.rejected_response = None
    elif len(clear) > 1:
        row.status = "uncertain"
        row.preference_reason = "ANNOTATION_CONFLICT"
        row.chosen_response = None
        row.rejected_response = None
    else:
        row.status = "annotated"
        row.chosen_response = row.response_a if body.choice == "a" else row.response_b
        row.rejected_response = row.response_b if body.choice == "a" else row.response_a
        row.preference_reason = body.reason
    audit(
        session,
        request,
        wid,
        user,
        "dpo.preference.annotate",
        "preference_sample",
        row.id,
        {"choice": body.choice},
    )
    session.commit()
    return {"preference_sample_id": row.id, "status": row.status}


def _review_source_evidence(
    session: Session,
    request: Request,
    workspace: str,
    user: str,
    evidence_ids: list[str],
    note: str,
) -> None:
    """Explicit independent review of exact immutable evidence; never an automatic quality pass."""
    if not evidence_ids or len(note.strip()) < 8:
        raise HTTPException(422, "VALIDATION_FAILED")
    unique = sorted(set(evidence_ids))
    rows = []
    for offset in range(0, len(unique), 500):
        rows.extend(
            session.scalars(
                select(Segment)
                .where(
                    Segment.workspace_id == workspace, Segment.id.in_(unique[offset : offset + 500])
                )
                .with_for_update()
            ).all()
        )
    if {row.id for row in rows} != set(unique):
        raise HTTPException(404, "NOT_FOUND")
    for row in rows:
        row.quality_state = "reviewed"
        audit(
            session,
            request,
            workspace,
            user,
            "quality.segment.review",
            "segment",
            row.id,
            {"decision": "reviewed", "content_hash": row.content_hash, "note": note},
        )


class DpoReviewIn(BaseModel):
    evidence_reviewed: bool = False
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(min_length=8, max_length=2000)
    choice: str | None = Field(default=None, pattern="^(a|b)$")


@router.post("/dpo/preferences/{preference_id}/review")
def review_dpo_preference(
    preference_id: str,
    body: DpoReviewIn,
    request: Request,
    session: Session = Depends(db),
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "reviewer"})
    row = session.scalar(
        select(PreferenceSample).where(
            PreferenceSample.id == preference_id, PreferenceSample.workspace_id == wid
        )
    )
    if not row:
        raise HTTPException(404, "NOT_FOUND")
    if row.published_version_id:
        raise HTTPException(409, "PREFERENCE_IMMUTABLE")
    annotators = set(
        session.scalars(
            select(PreferenceAnnotation.annotator_id).where(
                PreferenceAnnotation.preference_sample_id == row.id
            )
        )
    )
    if user == row.imported_by or user in annotators:
        raise HTTPException(409, "REVIEWER_SEPARATION_REQUIRED")
    if body.decision == "approved" and body.choice:
        row.chosen_response = row.response_a if body.choice == "a" else row.response_b
        row.rejected_response = row.response_b if body.choice == "a" else row.response_a
        row.status = "annotated"
        row.preference_reason = body.note
    if body.decision == "approved" and (
        row.status != "annotated" or not row.chosen_response or not row.rejected_response
    ):
        raise HTTPException(409, "PREFERENCE_NOT_RESOLVED")
    if body.evidence_reviewed:
        if body.decision != "approved":
            raise HTTPException(422, "VALIDATION_FAILED")
        _review_source_evidence(session, request, wid, user, list(row.evidence_ids), body.note)
    row.status = body.decision
    row.reviewed_by = user
    row.review_note = body.note
    audit(
        session,
        request,
        wid,
        user,
        "dpo.preference.review",
        "preference_sample",
        row.id,
        {"decision": body.decision},
    )
    session.commit()
    return {"preference_sample_id": row.id, "status": row.status}


class DpoBuildIn(BaseModel):
    dataset_id: str
    preference_sample_ids: list[str] = Field(min_length=1, max_length=500)
    config: dict[str, Any] = Field(default_factory=dict)


@router.post("/dpo/builds")
def create_dpo_build(body: DpoBuildIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    dataset = session.scalar(
        select(Dataset).where(
            Dataset.id == body.dataset_id,
            Dataset.workspace_id == wid,
            Dataset.product_type == "dpo",
        )
    )
    if not dataset:
        raise HTTPException(404, "NOT_FOUND")
    if len(set(body.preference_sample_ids)) != len(body.preference_sample_ids):
        raise HTTPException(422, "INVALID_PREFERENCE")
    preferences = list(
        session.scalars(
            select(PreferenceSample).where(
                PreferenceSample.workspace_id == wid,
                PreferenceSample.id.in_(body.preference_sample_ids),
            )
        )
    )
    if len(preferences) != len(body.preference_sample_ids):
        raise HTTPException(404, "NOT_FOUND")
    for preference in preferences:
        if preference.status != "approved":
            raise HTTPException(409, "PREFERENCE_NOT_RESOLVED")
        asset = _dpo_evidence_asset(
            session, wid, preference.source_id, [str(x) for x in preference.evidence_ids]
        )
        if not asset or not current_grant(session, wid, asset.id, "training"):
            raise HTTPException(409, "PURPOSE_GRANT_MISSING")
    builder = DpoBuilder()
    result = builder.build_preferences(preferences, body.config)
    if not result.candidates:
        raise HTTPException(409, "NO_VALID_CANDIDATES")
    cfg = {
        **body.config,
        "purpose": "training",
        "product_type": "dpo",
        "schema_version": "dpo.v1",
        "preference_sample_ids": sorted(body.preference_sample_ids),
        "excluded": result.excluded,
        "builder_metrics": result.metrics,
    }
    build = DatasetBuild(
        workspace_id=wid,
        dataset_id=dataset.id,
        created_by=user,
        config_json=cfg,
        config_hash=digest(cfg),
    )
    session.add(build)
    session.flush()
    for candidate in result.candidates:
        preference = next(
            item for item in preferences if item.id == candidate.payload["preference_sample_id"]
        )
        for evidence_id in candidate.evidence_ids:
            segment = session.get(Segment, evidence_id)
            if not segment:
                raise HTTPException(409, "INVALID_SAMPLE_EVIDENCE")
            session.add(
                BuildInput(
                    build_id=build.id,
                    segment_id=segment.id,
                    source_id=segment.source_id,
                    content_sha256=segment.content_hash,
                )
            )
        sample = CandidateSample(
            workspace_id=wid,
            build_id=build.id,
            sample_key=candidate.key,
            payload=candidate.payload,
            payload_hash=digest(candidate.payload),
            source_id=candidate.source_id,
            status="approved",
        )
        session.add(sample)
        session.flush()
        for evidence_id in candidate.evidence_ids:
            session.add(SampleEvidence(candidate_sample_id=sample.id, segment_id=evidence_id))
            edge(session, wid, "Segment", evidence_id, "CandidateSample", sample.id, "dpo_input")
        if preference.reviewed_by:
            session.add(
                SampleReview(
                    candidate_sample_id=sample.id,
                    reviewer_id=preference.reviewed_by,
                    decision="approved",
                    note=preference.review_note,
                )
            )
        edge(
            session,
            wid,
            "PreferenceSample",
            preference.id,
            "CandidateSample",
            sample.id,
            "built_from",
        )
    audit(session, request, wid, user, "dpo.build.create", "dataset_build", build.id)
    session.commit()
    return {
        "build_id": build.id,
        "dataset_id": dataset.id,
        "product_type": "dpo",
        "status": build.status,
        "candidate_count": len(result.candidates),
        "config_hash": build.config_hash,
        "metrics": result.metrics,
        "excluded": result.excluded,
    }


class PreviewIn(BaseModel):
    product_type: str = Field(default="sft", pattern="^(sft|pretrain|rag|evaluation)$")
    purpose: str = "training"
    segment_ids: list[str] = Field(default_factory=list)


@router.post("/dataset-builds/preview")
def build_preview(body: PreviewIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    builder = builder_for(body.product_type)
    if not builder:
        raise HTTPException(422, "UNSUPPORTED_PRODUCT_TYPE")
    if body.purpose != builder.purpose:
        raise HTTPException(409, "PRODUCT_PURPOSE_MISMATCH")
    segments = session.scalars(
        select(Segment).where(
            Segment.workspace_id == wid,
            Segment.id.in_(body.segment_ids) if body.segment_ids else True,
        )
    ).all()
    included = []
    excluded = []
    for seg in segments:
        asset = session.scalar(
            select(Asset)
            .join(Document, Document.asset_id == Asset.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.id == seg.document_version_id)
        )
        allowed = bool(asset and current_grant(session, wid, asset.id, body.purpose))
        (included if allowed else excluded).append(
            {"segment_id": seg.id, "reason": "grant_confirmed" if allowed else "grant_missing"}
        )
    return {
        "included": included,
        "excluded": excluded,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "metric_definition_version": "p0-1",
        "product_type": body.product_type,
        "schema_version": f"{body.product_type}.v1",
    }


class BuildIn(BaseModel):
    dataset_id: str
    segment_ids: list[str] = Field(min_length=1)
    purpose: str = Field(
        default="training", pattern="^(research|training|rag|evaluation|redistribute)$"
    )
    config: dict[str, Any] = Field(default_factory=dict)


@router.post("/dataset-builds")
def create_build(body: BuildIn, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "engineer"})
    dataset = session.scalar(
        select(Dataset).where(Dataset.id == body.dataset_id, Dataset.workspace_id == wid)
    )
    if not dataset:
        raise HTTPException(404, "NOT_FOUND")
    builder = builder_for(dataset.product_type)
    if not builder:
        raise HTTPException(422, "UNSUPPORTED_PRODUCT_TYPE")
    if body.purpose != builder.purpose:
        raise HTTPException(409, "PRODUCT_PURPOSE_MISMATCH")
    segments = session.scalars(
        select(Segment).where(Segment.workspace_id == wid, Segment.id.in_(body.segment_ids))
    ).all()
    authorized: list[Segment] = []
    excluded: list[dict[str, str]] = []
    for segment in segments:
        asset = session.scalar(
            select(Asset)
            .join(Document, Document.asset_id == Asset.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.id == segment.document_version_id, Asset.workspace_id == wid)
        )
        if asset and current_grant(session, wid, asset.id, body.purpose):
            authorized.append(segment)
        else:
            excluded.append({"segment_id": segment.id, "reason": "grant_missing"})
    if not authorized:
        raise HTTPException(409, "PURPOSE_GRANT_MISSING")
    try:
        result = builder.build(authorized, body.config)
    except BuilderError as exc:
        raise HTTPException(422, exc.code) from exc
    if not result.candidates:
        raise HTTPException(409, "NO_VALID_CANDIDATES")
    cfg = {
        **body.config,
        "purpose": body.purpose,
        "product_type": dataset.product_type,
        "schema_version": f"{dataset.product_type}.v1",
        "segment_ids": sorted(body.segment_ids),
        "authorized_segment_ids": sorted(item.id for item in authorized),
        "excluded": [*excluded, *result.excluded],
        "builder_metrics": result.metrics,
    }
    build = DatasetBuild(
        workspace_id=wid,
        dataset_id=dataset.id,
        created_by=user,
        config_json=cfg,
        config_hash=digest(cfg),
    )
    session.add(build)
    session.flush()
    count = 0
    for candidate in result.candidates:
        seg = (
            authorized[0]
            if not candidate.evidence_ids
            else next(
                (item for item in authorized if item.id == candidate.evidence_ids[0]), authorized[0]
            )
        )
        for evidence_id in candidate.evidence_ids:
            evidence_segment = next((item for item in authorized if item.id == evidence_id), seg)
            session.add(
                BuildInput(
                    build_id=build.id,
                    segment_id=evidence_id,
                    source_id=evidence_segment.source_id,
                    content_sha256=evidence_segment.content_hash,
                )
            )
        sample = CandidateSample(
            workspace_id=wid,
            build_id=build.id,
            sample_key=candidate.key,
            payload=candidate.payload,
            payload_hash=digest(candidate.payload),
            source_id=candidate.source_id,
        )
        session.add(sample)
        session.flush()
        for evidence_id in candidate.evidence_ids:
            session.add(SampleEvidence(candidate_sample_id=sample.id, segment_id=evidence_id))
            edge(session, wid, "Segment", evidence_id, "CandidateSample", sample.id, "generated")
        count += 1
    audit(session, request, wid, user, "dataset.build.create", "dataset_build", build.id)
    session.commit()
    return {
        "build_id": build.id,
        "config_hash": build.config_hash,
        "status": build.status,
        "candidate_count": count,
        "product_type": dataset.product_type,
        "excluded": cfg["excluded"],
        "metrics": result.metrics,
    }


class SampleReviewIn(BaseModel):
    evidence_reviewed: bool = False
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = ""


@router.post("/candidate-samples/{sample_id}/reviews")
def review_sample(
    sample_id: str, body: SampleReviewIn, request: Request, session: Session = Depends(db)
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin", "reviewer"})
    sample = session.scalar(
        select(CandidateSample).where(
            CandidateSample.id == sample_id, CandidateSample.workspace_id == wid
        )
    )
    if not sample:
        raise HTTPException(404, "NOT_FOUND")
    if (
        session.scalar(select(DatasetBuild.created_by).where(DatasetBuild.id == sample.build_id))
        == user
    ):
        raise HTTPException(403, "SELF_APPROVAL_FORBIDDEN")
    if session.scalar(
        select(DatasetVersionSample.id).where(DatasetVersionSample.candidate_sample_id == sample.id)
    ):
        raise HTTPException(409, "VERSION_CONFLICT")
    if body.evidence_reviewed:
        if body.decision != "approved":
            raise HTTPException(422, "VALIDATION_FAILED")
        evidence_ids = list(
            session.scalars(
                select(SampleEvidence.segment_id).where(
                    SampleEvidence.candidate_sample_id == sample.id
                )
            )
        )
        _review_source_evidence(session, request, wid, user, evidence_ids, body.note)
    sample.status = body.decision
    session.add(
        SampleReview(
            candidate_sample_id=sample.id, reviewer_id=user, decision=body.decision, note=body.note
        )
    )
    audit(
        session,
        request,
        wid,
        user,
        "dataset.sample.review",
        "candidate_sample",
        sample.id,
        {"decision": body.decision},
    )
    session.commit()
    return {"sample_id": sample.id, "status": sample.status}


@router.post("/dataset-builds/{build_id}/validate")
def validate_build(build_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    build = session.scalar(
        select(DatasetBuild).where(DatasetBuild.id == build_id, DatasetBuild.workspace_id == wid)
    )
    if not build:
        raise HTTPException(404, "NOT_FOUND")
    samples = session.scalars(
        select(CandidateSample).where(CandidateSample.build_id == build.id)
    ).all()
    checks = []
    for s in samples:
        checks.append(
            {
                "sample_id": s.id,
                "ok": s.status == "approved",
                "reason": "approved" if s.status == "approved" else "candidate_not_approved",
            }
        )
    ok = bool(samples) and all(c["ok"] for c in checks)
    build.status = "validated" if ok else "awaiting_review"
    build.validated_by = user if ok else None
    build.validated_snapshot_hash = (
        digest(
            {
                "config_hash": build.config_hash,
                "samples": sorted((s.id, s.payload_hash, s.status) for s in samples),
            }
        )
        if ok
        else None
    )
    session.commit()
    return {
        "build_id": build.id,
        "ok": ok,
        "checks": checks,
        "release_candidate_hash": digest([c for c in checks if c["ok"]]),
    }


@router.get("/dataset-builds/{build_id}/candidates")
def build_candidates(build_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = session.scalars(
        select(CandidateSample).where(
            CandidateSample.build_id == build_id,
            CandidateSample.workspace_id == wid,
        )
    ).all()
    return {
        "items": [
            {
                "sample_id": row.id,
                "evidence_ids": list(
                    session.scalars(
                        select(SampleEvidence.segment_id)
                        .where(SampleEvidence.candidate_sample_id == row.id)
                        .order_by(SampleEvidence.segment_id)
                    )
                ),
                "sample_key": row.sample_key,
                "status": row.status,
                "payload_hash": row.payload_hash,
                "payload": row.payload,
                "source_id": row.source_id,
            }
            for row in rows
        ]
    }


@router.get("/dataset-builds/{build_id}/quality-report")
def build_quality_report(build_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    build = session.scalar(
        select(DatasetBuild).where(DatasetBuild.id == build_id, DatasetBuild.workspace_id == wid)
    )
    if not build:
        raise HTTPException(404, "NOT_FOUND")
    samples = session.scalars(
        select(CandidateSample).where(CandidateSample.build_id == build.id)
    ).all()
    return {
        "build_id": build.id,
        "dataset_id": build.dataset_id,
        "product_type": build.config_json.get("product_type", "sft"),
        "status": build.status,
        "config_hash": build.config_hash,
        "metrics": build.config_json.get("builder_metrics", {}),
        "excluded": build.config_json.get("excluded", []),
        "candidate_count": len(samples),
        "approved_count": sum(sample.status == "approved" for sample in samples),
        "rejected_count": sum(sample.status == "rejected" for sample in samples),
    }


class PublishIn(BaseModel):
    build_id: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")


@router.post("/datasets/{dataset_id}/versions")
def publish(
    dataset_id: str,
    body: PublishIn,
    request: Request,
    session: Session = Depends(db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin"})
    dataset = session.scalar(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.workspace_id == wid)
    )
    build = session.scalar(
        select(DatasetBuild).where(
            DatasetBuild.id == body.build_id,
            DatasetBuild.dataset_id == dataset_id,
            DatasetBuild.workspace_id == wid,
        )
    )
    if not dataset or not build:
        raise HTTPException(404, "NOT_FOUND")
    _lock_dataset_version(session, dataset_id, body.version)
    existing = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.workspace_id == wid,
            DatasetVersion.version == body.version,
        )
    )
    if existing:
        return {"dataset_version_id": existing.id, "status": existing.status, "idempotent": True}
    if build.status != "validated":
        raise HTTPException(409, "RELEASE_GATE_FAILED")
    samples = session.scalars(
        select(CandidateSample).where(
            CandidateSample.build_id == build.id, CandidateSample.status == "approved"
        )
    ).all()
    reviewer_ids = {
        r.reviewer_id
        for s in samples
        for r in session.scalars(
            select(SampleReview).where(SampleReview.candidate_sample_id == s.id)
        ).all()
    }
    if user in reviewer_ids:
        raise HTTPException(409, "SELF_APPROVAL_FORBIDDEN")
    try:
        quality_run, quality_snapshot = evaluate_quality(
            session, wid, user, "dataset_build", build.id
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if quality_snapshot["quality_status"] != "PASS":
        audit(
            session,
            request,
            wid,
            user,
            "dataset.publish.quality_blocked",
            "quality_evaluation_run",
            quality_run.id,
        )
        session.commit()
        raise HTTPException(409, "QUALITY_GATE_FAILED")
    try:
        version, object_keys = materialize(
            session,
            request.app.state.config,
            wid,
            dataset,
            build,
            samples,
            user,
            body.version,
            quality_snapshot=quality_snapshot,
        )
    except MaterializationError as exc:
        raise HTTPException(409, exc.code) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "VERSION_CONFLICT") from exc
    audit(
        session,
        request,
        wid,
        user,
        "dataset.version.publish",
        "dataset_version",
        version.id,
        {"version": body.version},
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
        store = request.app.state.config
        from corpusflow.adapters.storage import S3ObjectStore

        storage = S3ObjectStore(
            store.object_store_endpoint,
            store.object_store_bucket,
            store.object_store_access_key.get_secret_value(),
            store.object_store_secret_key.get_secret_value(),
        )
        for key in object_keys:
            try:
                storage.delete(key)
            except Exception:
                pass
        raise
    from corpusflow.adapters.storage import S3ObjectStore

    storage = S3ObjectStore(
        request.app.state.config.object_store_endpoint,
        request.app.state.config.object_store_bucket,
        request.app.state.config.object_store_access_key.get_secret_value(),
        request.app.state.config.object_store_secret_key.get_secret_value(),
    )
    for key in object_keys[:2]:
        try:
            storage.delete(key)
        except Exception:
            pass
    return {
        "dataset_version_id": version.id,
        "status": version.status,
        "manifest_sha256": version.manifest_sha256,
        "content_sha256": version.content_sha256,
        "sample_count": version.sample_count,
        "content_storage_key": version.content_storage_key,
    }


def _version_authorized(session: Session, wid: str, version: DatasetVersion, purpose: str) -> bool:
    samples = session.scalars(
        select(CandidateSample)
        .join(DatasetVersionSample, DatasetVersionSample.candidate_sample_id == CandidateSample.id)
        .where(DatasetVersionSample.dataset_version_id == version.id)
    ).all()
    assets: list[Asset] = []
    seen: set[str] = set()
    for sample in samples:
        for evidence_id in sample.payload.get("evidence_ids", []):
            asset = session.scalar(
                select(Asset)
                .join(Document, Document.asset_id == Asset.id)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .join(Segment, Segment.document_version_id == DocumentVersion.id)
                .where(Segment.id == str(evidence_id), Asset.workspace_id == wid)
            )
            if asset and asset.id not in seen:
                seen.add(asset.id)
                assets.append(asset)
    if not assets:
        return False
    return all(
        session.scalar(
            select(LicenseGrant.id).where(
                LicenseGrant.workspace_id == wid,
                LicenseGrant.asset_id == asset.id,
                LicenseGrant.purpose == purpose,
                LicenseGrant.status == "confirmed",
            )
        )
        for asset in assets
    )


def _lock_dataset_version(session: Session, dataset_id: str, version: str) -> None:
    """Serialize publication attempts for one immutable dataset version."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"dataset-version:{dataset_id}:{version}"},
        )


@router.get("/datasets/{dataset_id}/versions")
def list_versions(dataset_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    if not session.scalar(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.workspace_id == wid)
    ):
        raise HTTPException(404, "NOT_FOUND")
    rows = session.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.workspace_id == wid)
        .order_by(DatasetVersion.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "dataset_version_id": row.id,
                "version": row.version,
                "status": row.status,
                "sample_count": row.sample_count,
                "content_sha256": row.content_sha256,
                "manifest_sha256": row.manifest_sha256,
                "published_at": row.published_at.isoformat() if row.published_at else None,
            }
            for row in rows
        ]
    }


@router.get("/datasets/{dataset_id}/versions/{version}/manifest")
def get_manifest(dataset_id: str, version: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version == version,
            DatasetVersion.workspace_id == wid,
            DatasetVersion.status == "published",
        )
    )
    if not row:
        raise HTTPException(404, "DATASET_VERSION_NOT_FOUND")
    try:
        from corpusflow.adapters.storage import S3ObjectStore

        storage = S3ObjectStore(
            request.app.state.config.object_store_endpoint,
            request.app.state.config.object_store_bucket,
            request.app.state.config.object_store_access_key.get_secret_value(),
            request.app.state.config.object_store_secret_key.get_secret_value(),
        )
        return json.loads(storage.get(row.manifest_storage_key))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "ADAPTER_UNAVAILABLE") from exc


@router.get("/datasets/{dataset_id}/versions/{version}/download")
def get_download(
    dataset_id: str,
    version: str,
    request: Request,
    session: Session = Depends(db),
    purpose: str = "training",
):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    row = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version == version,
            DatasetVersion.workspace_id == wid,
            DatasetVersion.status == "published",
        )
    )
    if not row:
        raise HTTPException(404, "DATASET_VERSION_NOT_FOUND")
    if not _version_authorized(session, wid, row, purpose):
        raise HTTPException(403, "DOWNLOAD_NOT_AUTHORIZED")
    from corpusflow.adapters.storage import S3ObjectStore

    storage = S3ObjectStore(
        request.app.state.config.object_store_endpoint,
        request.app.state.config.object_store_bucket,
        request.app.state.config.object_store_access_key.get_secret_value(),
        request.app.state.config.object_store_secret_key.get_secret_value(),
    )
    try:
        url = storage.presign_get(row.content_storage_key, 300)
    except Exception as exc:
        raise HTTPException(503, "ADAPTER_UNAVAILABLE") from exc
    audit(
        session,
        request,
        wid,
        user,
        "dataset.version.download",
        "dataset_version",
        row.id,
        {"purpose": purpose},
    )
    session.commit()
    return {
        "dataset_version_id": row.id,
        "version": row.version,
        "url": url,
        "expires_in": 300,
        "purpose": purpose,
    }


@router.get("/lineage/{object_type}/{object_id}")
def lineage(object_type: str, object_id: str, request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    rows = session.scalars(
        select(LineageEdge).where(
            LineageEdge.workspace_id == wid,
            ((LineageEdge.from_type == object_type) & (LineageEdge.from_id == object_id))
            | ((LineageEdge.to_type == object_type) & (LineageEdge.to_id == object_id)),
        )
    ).all()
    return {
        "object_type": object_type,
        "object_id": object_id,
        "edges": [
            {
                "from_type": e.from_type,
                "from_id": e.from_id,
                "to_type": e.to_type,
                "to_id": e.to_id,
                "relation": e.relation,
            }
            for e in rows
        ],
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/demo/cases")
def demo_cases(request: Request, session: Session = Depends(db)):
    """Expose an index of real records suitable for a read-only visitor demo."""
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    latest_run = session.scalar(
        select(PipelineRun)
        .where(
            PipelineRun.workspace_id == wid,
            PipelineRun.status.in_(["succeeded", "awaiting_review"]),
        )
        .order_by(PipelineRun.finished_at.desc().nullslast(), PipelineRun.created_at.desc())
    )
    normal_objects: dict[str, str | None] = {
        "pipeline_run_id": latest_run.id if latest_run else None
    }
    if latest_run:
        asset = session.scalar(
            select(Asset).where(Asset.id == latest_run.asset_id, Asset.workspace_id == wid)
        )
        normal_objects["asset_id"] = asset.id if asset else None
        document = session.scalar(
            select(Document).where(
                Document.asset_id == latest_run.asset_id, Document.workspace_id == wid
            )
        )
        normal_objects["document_id"] = document.id if document else None
        if document:
            version = session.scalar(
                select(DocumentVersion)
                .where(
                    DocumentVersion.document_id == document.id, DocumentVersion.workspace_id == wid
                )
                .order_by(DocumentVersion.version_no.desc())
            )
            normal_objects["document_version_id"] = version.id if version else None
            if version:
                dataset_version = session.scalar(
                    select(DatasetVersion)
                    .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
                    .where(DatasetVersion.workspace_id == wid, DatasetVersion.status == "published")
                    .order_by(DatasetVersion.created_at.desc())
                )
                normal_objects["dataset_version_id"] = (
                    dataset_version.id if dataset_version else None
                )

    historical = {
        "retrieval_trace_id": "83551145-7804-4bdd-ab42-094a799cf3d5",
        "segment_id": "31433147-00a2-4ab2-ac98-f9b4fe74f208",
        "feedback_id": "01d87232-5541-458e-b5e4-3c0eeb20bb5c",
        "pipeline_run_id": "b2fb6950-30cd-49f4-b51b-030426810e5a",
        "document_version_id": "b1a6e7df-8132-4ebd-86c2-113e38ee6aea",
        "dataset_version_id": "612f8414-d119-4e13-91f7-f0c58e78f5b3",
        "index_version_id": "dea6432a-df26-4811-99ae-07d10b092f44",
        "fts_evaluation_id": "e97097a4-9786-446f-ad0c-dda4faa82a89",
        "bm25_evaluation_id": "340b2ddf-a5ed-441a-b628-041e3915d08e",
    }
    from corpusflow.db.models import RagEvaluationRun, RagFeedback, RagIndexVersion, RetrievalTrace

    historical_models: dict[str, Any] = {
        "retrieval_trace_id": RetrievalTrace,
        "segment_id": Segment,
        "feedback_id": RagFeedback,
        "pipeline_run_id": PipelineRun,
        "document_version_id": DocumentVersion,
        "dataset_version_id": DatasetVersion,
        "index_version_id": RagIndexVersion,
        "fts_evaluation_id": RagEvaluationRun,
        "bm25_evaluation_id": RagEvaluationRun,
    }
    historical_presence = {
        key: bool(
            session.scalar(select(model.id).where(model.id == value, model.workspace_id == wid))
        )
        for key, value in historical.items()
        for model in [historical_models[key]]
    }

    def evaluation_metrics(evaluation_id: str) -> dict[str, Any] | None:
        evaluation = session.scalar(
            select(RagEvaluationRun).where(
                RagEvaluationRun.id == evaluation_id,
                RagEvaluationRun.workspace_id == wid,
            )
        )
        if not evaluation:
            return None
        report = evaluation.report if isinstance(evaluation.report, dict) else {}
        metrics = report.get("metrics", {})
        return {
            "recall_at_3": metrics.get("recall_at_3"),
            "mrr": metrics.get("mrr"),
            "precision_at_3": metrics.get("precision_at_3"),
            "source": "RagEvaluationRun.report",
        }

    return {
        "items": [
            {
                "case_id": "latest-processing-chain",
                "title": "当前 workspace 最近一次真实处理链路",
                "status": "AVAILABLE" if latest_run else "NOT_AVAILABLE",
                "description": "从真实 Asset、PipelineRun、DocumentVersion 到最近发布版本的入口。",
                "objects": normal_objects,
                "limitations": ["对象入口随 workspace 数据变化；没有数据时不创建演示对象"],
            },
            {
                "case_id": "kem-feedback-rework",
                "title": "KEM encapsulation 反馈与重工",
                "status": "AVAILABLE" if all(historical_presence.values()) else "MISSING",
                "description": "固定历史证据只在当前 workspace 中存在时展示；缺失对象不会被伪造。",
                "objects": historical,
                "presence": historical_presence,
                "metrics": {
                    "fts": evaluation_metrics(historical["fts_evaluation_id"]),
                    "bm25": evaluation_metrics(historical["bm25_evaluation_id"]),
                },
                "limitations": ["重工未改善 FTS；BM25 是同一新版本上的独立检索策略结果"],
            },
        ],
        "scope": {"workspace_id": wid},
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/audit-events")
def audit_events(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin"})
    rows = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.workspace_id == wid)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    ).all()
    return {
        "items": [
            {
                "event_id": e.id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "actor_id": e.actor_id,
                "summary": e.summary,
            }
            for e in rows
        ]
    }


@router.get("/ops/metrics")
def ops_metrics(request: Request, session: Session = Depends(db)):
    user = actor_id(request, session)
    wid = workspace_id(request, session, user)
    role_required(session, user, wid, {"admin"})
    run_counts = dict(
        session.execute(
            select(PipelineRun.status, func.count(PipelineRun.id))
            .where(PipelineRun.workspace_id == wid)
            .group_by(PipelineRun.status)
        ).all()
    )
    outbox_counts = dict(
        session.execute(
            select(OutboxEvent.status, func.count(OutboxEvent.id))
            .where(OutboxEvent.workspace_id == wid)
            .group_by(OutboxEvent.status)
        ).all()
    )
    retry_count = session.scalar(
        select(func.coalesce(func.sum(OutboxEvent.attempts), 0)).where(
            OutboxEvent.workspace_id == wid
        )
    )
    runs_with_duration = session.scalars(
        select(PipelineRun).where(
            PipelineRun.workspace_id == wid,
            PipelineRun.started_at.is_not(None),
            PipelineRun.finished_at.is_not(None),
        )
    ).all()
    durations = [
        (run.finished_at - run.started_at).total_seconds() * 1000
        for run in runs_with_duration
        if run.started_at and run.finished_at
    ]
    return {
        "workspace_id": wid,
        "pipeline_runs": {str(key): int(value) for key, value in run_counts.items()},
        "outbox": {str(key): int(value) for key, value in outbox_counts.items()},
        "outbox_attempts": int(retry_count or 0),
        "execution_duration_ms": {
            "completed_runs": len(durations),
            "average": round(sum(durations) / len(durations), 2) if durations else None,
            "max": round(max(durations), 2) if durations else None,
        },
        "published_versions": int(
            session.scalar(
                select(func.count(DatasetVersion.id)).where(
                    DatasetVersion.workspace_id == wid,
                    DatasetVersion.status == "published",
                )
            )
            or 0
        ),
    }
