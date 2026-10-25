from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from corpusflow.adapters.processing import (
    BUILTIN_PROCESSORS,
    ProcessingAdapter,
    ProcessingError,
    ProcessingResult,
)
from corpusflow.db.models import DocumentVersion, LineageEdge, Segment


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def segment_records(session: Session, document_version_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(Segment)
        .where(Segment.document_version_id == document_version_id)
        .order_by(Segment.created_at, Segment.id)
    ).all()
    return [
        {
            "segment_id": row.id,
            "text": row.text,
            "content_hash": row.content_hash,
            "source_id": row.source_id,
            "location": row.location_json,
            "section_title": row.section_title,
        }
        for row in rows
    ]


def run_processor(
    operator_key: str, records: list[dict[str, Any]], config: dict[str, Any]
) -> ProcessingResult:
    processor_type = BUILTIN_PROCESSORS.get(operator_key)
    if not processor_type:
        raise ProcessingError("OPERATOR_NOT_FOUND", f"unknown operator: {operator_key}")
    processor = cast(type[ProcessingAdapter], processor_type)()
    return processor.process(records, config)


def create_derived_version(
    session: Session,
    workspace_id: str,
    source_version: DocumentVersion,
    run_id: str,
    result: ProcessingResult,
    operator_config: dict[str, Any],
) -> DocumentVersion:
    next_no = (
        int(
            session.scalar(
                select(func.coalesce(func.max(DocumentVersion.version_no), 0)).where(
                    DocumentVersion.document_id == source_version.document_id,
                    DocumentVersion.workspace_id == workspace_id,
                )
            )
            or 0
        )
        + 1
    )
    content = "\n\n".join(str(record["text"]) for record in result.records)
    derived = DocumentVersion(
        workspace_id=workspace_id,
        document_id=source_version.document_id,
        version_no=next_no,
        content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        parser_name=result.operator_key,
        parser_version=result.operator_version,
        config_hash=config_hash(operator_config),
        run_id=run_id,
        status="succeeded",
    )
    session.add(derived)
    session.flush()
    session.add(
        LineageEdge(
            workspace_id=workspace_id,
            from_type="DocumentVersion",
            from_id=source_version.id,
            to_type="DocumentVersion",
            to_id=derived.id,
            relation="transformed_to",
        )
    )
    for record in result.records:
        text = str(record["text"])
        segment = Segment(
            workspace_id=workspace_id,
            document_version_id=derived.id,
            source_id=str(record["source_id"]),
            text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            quality_state="unreviewed",
            location_json=record.get("location") or {},
            token_count=len(text.split()),
            section_title=record.get("section_title"),
        )
        session.add(segment)
        session.flush()
        session.add(
            LineageEdge(
                workspace_id=workspace_id,
                from_type="DocumentVersion",
                from_id=source_version.id,
                to_type="Segment",
                to_id=segment.id,
                relation="transformed_segment",
            )
        )
        session.add(
            LineageEdge(
                workspace_id=workspace_id,
                from_type="Segment",
                from_id=segment.id,
                to_type="DocumentVersion",
                to_id=derived.id,
                relation="contained_in",
            )
        )
    return derived
