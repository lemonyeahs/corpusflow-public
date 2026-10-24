from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from corpusflow.adapters.parser import HTMLParserAdapter, ParserError, PDFParserAdapter
from corpusflow.adapters.storage import S3ObjectStore
from corpusflow.core.config import Settings, load_settings
from corpusflow.db.models import (
    Artifact,
    Asset,
    AssetBlob,
    DatasetVersion,
    Document,
    DocumentVersion,
    ExecutionLog,
    LineageEdge,
    NodeRun,
    PipelineRun,
    Segment,
)
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app

log = logging.getLogger(__name__)


def _session() -> sessionmaker[Session]:
    return sessionmaker(build_engine(load_settings()), expire_on_commit=False)


def _write_log(
    session: Session,
    run: PipelineRun,
    message: str,
    level: str = "INFO",
    node_id: str | None = None,
    attempt: int = 1,
) -> None:
    node = session.scalar(
        select(NodeRun).where(NodeRun.run_id == run.id, NodeRun.node_id == (node_id or "parse"))
    )
    session.add(
        ExecutionLog(
            workspace_id=run.workspace_id,
            run_id=run.id,
            node_run_id=node.id if node else None,
            level=level,
            message=message[:2000],
            attempt_no=attempt,
        )
    )


def _store(settings: Settings, key: str, body: bytes, content_type: str) -> None:
    S3ObjectStore(
        settings.object_store_endpoint,
        settings.object_store_bucket,
        settings.object_store_access_key.get_secret_value(),
        settings.object_store_secret_key.get_secret_value(),
    ).put(key, body, content_type)


@celery_app.task(bind=True, name="corpusflow.execute_pipeline_run", max_retries=3, acks_late=True)  # type: ignore[untyped-decorator]
def execute_pipeline_run(self: Any, run_id: str) -> dict[str, str]:
    settings = load_settings()
    factory = _session()
    with factory() as session:
        run = session.scalar(select(PipelineRun).where(PipelineRun.id == run_id).with_for_update())
        if not run:
            return {"run_id": run_id, "status": "missing"}
        if run.status == "succeeded":
            return {"run_id": run.id, "status": run.status}
        if run.status in {"awaiting_review", "rejected", "isolated"}:
            return {"run_id": run.id, "status": run.status}
        node = session.scalar(
            select(NodeRun)
            .where(NodeRun.run_id == run.id, NodeRun.node_id == "parse")
            .order_by(NodeRun.attempt_no.desc())
        )
        if not node:
            node = NodeRun(run_id=run.id, node_id="parse", status="pending")
            session.add(node)
            session.flush()
        elif node.status == "failed":
            node = NodeRun(
                run_id=run.id,
                node_id="parse",
                attempt_no=node.attempt_no + 1,
                status="pending",
            )
            session.add(node)
            session.flush()
        if node.status == "succeeded":
            run.status = "succeeded"
            session.commit()
            return {"run_id": run.id, "status": run.status}
        node.status = "running"
        run.status = "running"
        run.started_at = run.started_at or datetime.now(UTC)
        attempt = node.attempt_no
        session.commit()

        try:
            asset = session.scalar(select(Asset).where(Asset.id == run.asset_id))
            blob = (
                session.scalar(select(AssetBlob).where(AssetBlob.id == asset.blob_id))
                if asset
                else None
            )
            if not asset or not blob:
                raise ParserError("INPUT_NOT_FOUND", "asset or object metadata missing")
            content = S3ObjectStore(
                settings.object_store_endpoint,
                settings.object_store_bucket,
                settings.object_store_access_key.get_secret_value(),
                settings.object_store_secret_key.get_secret_value(),
            ).get(blob.storage_key)
            parser = (
                PDFParserAdapter()
                if asset.format.lower() == "pdf" or blob.media_type == "application/pdf"
                else HTMLParserAdapter()
            )
            result = parser.parse(content, asset.filename, blob.media_type)
            markdown_key = f"artifacts/{run.id}/document.md"
            json_key = f"artifacts/{run.id}/document.json"
            _store(settings, markdown_key, result.markdown.encode(), "text/markdown")
            _store(
                settings,
                json_key,
                json.dumps(result.structured, ensure_ascii=False).encode(),
                "application/json",
            )
            existing = session.scalar(
                select(DocumentVersion)
                .join(Document)
                .where(
                    Document.asset_id == asset.id,
                    Document.workspace_id == run.workspace_id,
                    DocumentVersion.content_sha256 == result.input_sha256,
                    DocumentVersion.parser_version == result.parser_version,
                )
            )
            if existing:
                dv = existing
            else:
                doc = session.scalar(
                    select(Document).where(
                        Document.asset_id == asset.id, Document.workspace_id == run.workspace_id
                    )
                )
                if not doc:
                    doc = Document(
                        workspace_id=run.workspace_id, asset_id=asset.id, title=asset.filename
                    )
                    session.add(doc)
                    session.flush()
                dv = DocumentVersion(
                    workspace_id=run.workspace_id,
                    document_id=doc.id,
                    version_no=1,
                    content_sha256=result.input_sha256,
                    parser_version=result.parser_version,
                )
                session.add(dv)
                session.flush()
                for section in result.sections:
                    seg = Segment(
                        workspace_id=run.workspace_id,
                        document_version_id=dv.id,
                        source_id=asset.source_id,
                        text=section.text,
                        content_hash=hashlib.sha256(section.text.encode()).hexdigest(),
                    )
                    session.add(seg)
                    session.flush()
                    session.add(
                        LineageEdge(
                            workspace_id=run.workspace_id,
                            from_type="DocumentVersion",
                            from_id=dv.id,
                            to_type="Segment",
                            to_id=seg.id,
                            relation="contains",
                        )
                    )
                session.add(
                    LineageEdge(
                        workspace_id=run.workspace_id,
                        from_type="Asset",
                        from_id=asset.id,
                        to_type="DocumentVersion",
                        to_id=dv.id,
                        relation="parsed_to",
                    )
                )
            session.add(
                LineageEdge(
                    workspace_id=run.workspace_id,
                    from_type="Asset",
                    from_id=asset.id,
                    to_type="PipelineRun",
                    to_id=run.id,
                    relation="processed_by",
                )
            )
            session.add(
                LineageEdge(
                    workspace_id=run.workspace_id,
                    from_type="PipelineRun",
                    from_id=run.id,
                    to_type="DocumentVersion",
                    to_id=dv.id,
                    relation="produced",
                )
            )
            if not session.scalar(
                select(Artifact).where(
                    Artifact.run_id == run.id, Artifact.kind == "document_markdown"
                )
            ):
                session.add(
                    Artifact(
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        kind="document_markdown",
                        storage_key=markdown_key,
                        content_sha256=hashlib.sha256(result.markdown.encode()).hexdigest(),
                    )
                )
                session.add(
                    Artifact(
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        kind="document_json",
                        storage_key=json_key,
                        content_sha256=hashlib.sha256(
                            json.dumps(result.structured, ensure_ascii=False).encode()
                        ).hexdigest(),
                    )
                )
            node.status = "succeeded"
            run.status = "succeeded"
            run.finished_at = datetime.now(UTC)
            run.error_code = None
            _write_log(
                session,
                run,
                f"parsed {result.parser} sections={len(result.sections)} "
                f"bytes={result.input_bytes}",
                attempt=attempt,
            )
            session.commit()
            return {"run_id": run.id, "status": run.status, "parser": result.parser}
        except ParserError as exc:
            node.status = "failed"
            run.status = "failed"
            run.error_code = exc.code
            run.finished_at = datetime.now(UTC)
            _write_log(session, run, f"parser failure {exc.code}", level="ERROR", attempt=attempt)
            session.commit()
            return {"run_id": run.id, "status": run.status, "error_code": exc.code}
        except Exception as exc:
            session.rollback()
            with factory() as retry_session:
                retry_run = retry_session.scalar(
                    select(PipelineRun).where(PipelineRun.id == run_id).with_for_update()
                )
                if retry_run:
                    retries = int(getattr(getattr(self, "request", None), "retries", 0))
                    retry_run.status = "queued" if retries < 3 else "failed"
                    retry_run.error_code = "PROCESSING_RETRY" if retries < 3 else "PROCESSING_ERROR"
                    retry_run.finished_at = datetime.now(UTC) if retries >= 3 else None
                    _write_log(
                        retry_session,
                        retry_run,
                        f"processing failure {type(exc).__name__}; retry={retries < 3}",
                        level="ERROR",
                        attempt=attempt,
                    )
                    retry_session.commit()
            log.exception("pipeline_run_failed", extra={"run_id": run_id})
            retries = int(getattr(getattr(self, "request", None), "retries", 0))
            if retries < 3:
                raise self.retry(exc=exc, countdown=min(60, 2**retries)) from exc
            raise


@celery_app.task(name="corpusflow.deliver_dataset_version", acks_late=True)  # type: ignore[untyped-decorator]
def deliver_dataset_version(dataset_version_id: str) -> dict[str, str]:
    """Acknowledge an immutable version delivery event without mutating content."""
    factory = _session()
    with factory() as session:
        version = session.scalar(
            select(DatasetVersion).where(DatasetVersion.id == dataset_version_id)
        )
        if not version:
            return {"dataset_version_id": dataset_version_id, "status": "missing"}
        if version.status != "published":
            return {"dataset_version_id": version.id, "status": version.status}
        return {"dataset_version_id": version.id, "status": "delivered"}
