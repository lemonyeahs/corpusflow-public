from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from corpusflow.adapters.parser import (
    HTMLParserAdapter,
    ParserError,
    PDFParserAdapter,
    TextParserAdapter,
)
from corpusflow.adapters.parser.base import ParserAdapter
from corpusflow.adapters.parser.layout import LayoutParserAdapter
from corpusflow.adapters.parser.ocr import OCRParserAdapter
from corpusflow.adapters.processing import ProcessingError
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
from corpusflow.services.processing_pipeline import (
    create_derived_version,
    run_processor,
    segment_records,
)
from corpusflow.services.quality_rework import resolve_reworked_issues
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
        select(NodeRun)
        .where(NodeRun.run_id == run.id, NodeRun.node_id == (node_id or "parse"))
        .order_by(NodeRun.attempt_no.desc())
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


def _run_processing_chain(
    session: Session,
    settings: Settings,
    run: PipelineRun,
    source_version: DocumentVersion,
) -> DocumentVersion:
    """Run the immutable, versioned post-parse operators for one Run."""
    pipeline_config = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
    configured = pipeline_config.get("operators")
    operators = (
        configured
        if isinstance(configured, list)
        else [
            {"key": "builtin.clean", "config": {}},
            {"key": "builtin.deduplicate", "config": {}},
            {"key": "builtin.quality", "config": {}},
        ]
    )
    current = source_version
    for spec in operators:
        operator_config: dict[str, Any] = {}
        if isinstance(spec, str):
            key = spec
        elif isinstance(spec, dict):
            key = str(spec.get("key", ""))
            raw_config = spec.get("config", {})
            if not isinstance(raw_config, dict):
                raise ProcessingError(
                    "PROCESSING_CONFIG_INVALID", f"config for {key} must be an object"
                )
            operator_config = dict(raw_config)
        else:
            raise ProcessingError("PROCESSING_CONFIG_INVALID", "operator specification is invalid")
        if not key:
            raise ProcessingError("PROCESSING_CONFIG_INVALID", "operator key is empty")
        node_id = key.rsplit(".", 1)[-1]
        node = session.scalar(
            select(NodeRun)
            .where(NodeRun.run_id == run.id, NodeRun.node_id == node_id)
            .order_by(NodeRun.attempt_no.desc())
        )
        if node and node.status == "succeeded":
            continue
        if not node:
            node = NodeRun(
                run_id=run.id,
                node_id=node_id,
                status="pending",
                operator_key=key,
                operator_version="builtin",
                config_snapshot=operator_config,
            )
            session.add(node)
            session.flush()
        node.status = "running"
        node.operator_key = key
        node.config_snapshot = operator_config
        node.input_count = len(segment_records(session, current.id))
        started = datetime.now(UTC)
        session.commit()
        try:
            records = segment_records(session, current.id)
            result = run_processor(key, records, operator_config)
            node.operator_version = result.operator_version
            node.output_count = len(result.records)
            node.filtered_count = result.filtered_count
            node.duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
            prefix = (
                f"artifacts/{run.id}"
                if node.attempt_no == 1
                else f"artifacts/{run.id}/attempt-{node.attempt_no}"
            )
            artifact_key = f"{prefix}/{node_id}/output.json"
            artifact_kind = (
                f"operator_{node_id}"
                if node.attempt_no == 1
                else f"operator_{node_id}_attempt_{node.attempt_no}"
            )
            payload = json.dumps(
                {
                    "operator": key,
                    "version": result.operator_version,
                    "config": result.config_snapshot,
                    "metrics": result.metrics,
                    "records": result.records,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            _store(settings, artifact_key, payload, "application/json")
            artifact = session.scalar(
                select(Artifact).where(Artifact.run_id == run.id, Artifact.kind == artifact_kind)
            )
            if not artifact:
                artifact = Artifact(
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    kind=artifact_kind,
                    storage_key=artifact_key,
                    content_sha256=hashlib.sha256(payload).hexdigest(),
                )
                session.add(artifact)
                session.flush()
            node.log_ref = artifact_key
            if key != "builtin.quality" and result.records != records:
                current = create_derived_version(
                    session, run.workspace_id, current, run.id, result, operator_config
                )
            if key == "builtin.quality" and operator_config.get("create_issues", False):
                short_count = int(result.metrics.get("short_records", 0))
                if short_count:
                    from corpusflow.db.models import QualityIssue

                    session.add(
                        QualityIssue(
                            workspace_id=run.workspace_id,
                            run_id=run.id,
                            asset_id=run.asset_id,
                            status="open",
                            severity="medium",
                            reason=f"{short_count} segments below minimum length",
                            rule_version=result.operator_version,
                        )
                    )
            node.status = "succeeded"
            _write_log(
                session,
                run,
                f"operator {key} input={node.input_count} output={node.output_count} "
                f"filtered={node.filtered_count}",
                node_id=node_id,
            )
            session.commit()
        except ProcessingError as exc:
            session.rollback()
            failed = session.scalar(select(NodeRun).where(NodeRun.id == node.id))
            if failed:
                failed.status = "failed"
                failed.failure_code = exc.code
                failed.duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
                _write_log(session, run, f"operator failure {exc.code}", "ERROR", node_id=node_id)
                session.commit()
            raise
    return current


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
            asset_format = asset.format.lower()
            media_type = blob.media_type.split(";", 1)[0].strip().lower()
            if asset_format == "pdf" or media_type == "application/pdf":
                parser: ParserAdapter = PDFParserAdapter()
            elif asset_format in {"html", "htm"} or media_type in {
                "text/html",
                "application/xhtml+xml",
            }:
                parser = HTMLParserAdapter()
            elif (
                asset_format in {"txt", "md", "markdown", "mdown", "mkdn"}
                or media_type.startswith("text/")
            ):
                parser = TextParserAdapter()
            else:
                # TextParserAdapter performs strict binary/encoding validation for unknown
                # extensions, preserving the existing adapter error contract.
                parser = TextParserAdapter()
            parser_kind = run.config_snapshot.get("parser", "builtin")
            if parser_kind not in {"builtin", "ocr", "layout"}:
                raise ParserError("PARSER_CONFIG_INVALID", "Unknown parser")
            if parser_kind in {"ocr", "layout"}:
                if asset.format.lower() != "pdf":
                    raise ParserError("UNSUPPORTED_FORMAT", "OCR requires PDF")
                parser = OCRParserAdapter() if parser_kind == "ocr" else LayoutParserAdapter()
            node.operator_key = parser.name
            node.operator_version = parser.version
            node.config_snapshot = {"parser": parser_kind, "version": parser.version}
            parse_started = datetime.now(UTC)
            result = parser.parse(content, asset.filename, blob.media_type)
            node.duration_ms = (datetime.now(UTC) - parse_started).total_seconds() * 1000
            node.input_count = 1
            node.output_count = len(result.sections)
            prefix = (
                f"artifacts/{run.id}" if attempt == 1 else f"artifacts/{run.id}/attempt-{attempt}"
            )
            markdown_key = f"{prefix}/document.md"
            json_key = f"{prefix}/document.json"
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
                    DocumentVersion.parser_name == result.parser,
                    DocumentVersion.config_hash
                    == hashlib.sha256(
                        json.dumps(run.config_snapshot, sort_keys=True).encode()
                    ).hexdigest(),
                )
            )
            if existing and attempt == 1:
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
                    version_no=int(
                        session.scalar(
                            select(func.coalesce(func.max(DocumentVersion.version_no), 0)).where(
                                DocumentVersion.document_id == doc.id,
                                DocumentVersion.workspace_id == run.workspace_id,
                            )
                        )
                        or 0
                    )
                    + 1,
                    content_sha256=result.input_sha256,
                    parser_version=result.parser_version,
                    parser_name=result.parser,
                    config_hash=hashlib.sha256(
                        json.dumps(run.config_snapshot, sort_keys=True).encode()
                    ).hexdigest(),
                    run_id=run.id,
                    status="succeeded",
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
                        location_json=section.location,
                        token_count=len(section.text.split()),
                        section_title=section.title,
                    )
                    session.add(seg)
                    session.flush()
                    if attempt > 1:
                        previous = session.scalars(
                            select(Segment)
                            .join(DocumentVersion)
                            .where(
                                DocumentVersion.document_id == doc.id,
                                Segment.document_version_id != dv.id,
                                Segment.content_hash == seg.content_hash,
                                Segment.workspace_id == run.workspace_id,
                            )
                        ).all()
                        for old_segment in previous:
                            if old_segment.location_json == seg.location_json:
                                session.add(
                                    LineageEdge(
                                        workspace_id=run.workspace_id,
                                        from_type="Segment",
                                        from_id=old_segment.id,
                                        to_type="Segment",
                                        to_id=seg.id,
                                        relation="reprocessed_equivalent",
                                    )
                                )
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
                    Artifact.run_id == run.id, Artifact.storage_key == markdown_key
                )
            ):
                session.add(
                    Artifact(
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        kind="document_markdown"
                        if attempt == 1
                        else f"document_markdown_attempt_{attempt}",
                        storage_key=markdown_key,
                        content_sha256=hashlib.sha256(result.markdown.encode()).hexdigest(),
                    )
                )
                session.add(
                    Artifact(
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        kind="document_json"
                        if attempt == 1
                        else f"document_json_attempt_{attempt}",
                        storage_key=json_key,
                        content_sha256=hashlib.sha256(
                            json.dumps(result.structured, ensure_ascii=False).encode()
                        ).hexdigest(),
                    )
                )
            _run_processing_chain(session, settings, run, dv)
            node.status = "succeeded"
            session.flush()
            run.status = "succeeded" if resolve_reworked_issues(session, run) else "awaiting_review"
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
        except (ParserError, ProcessingError) as exc:
            node.failure_code = exc.code
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


@celery_app.task(bind=True, name="corpusflow.rag_job", max_retries=3, acks_late=True)  # type: ignore[untyped-decorator]
def rag_job(self: Any, object_id: str) -> dict[str, str]:
    """Atomic bounded job: lock, compute and commit; crashes roll back partial rows.

    Redelivery resumes queued/running work. Terminal failures require a new request
    key, preserving the failed attempt for diagnostics.
    """
    from corpusflow.db.models import RagEvaluationRun, RagIndexVersion
    from corpusflow.services import rag

    factory = _session()
    with factory() as session:
        row = session.scalar(
            select(RagIndexVersion).where(RagIndexVersion.id == object_id).with_for_update()
        )
        if row is None:
            evaluation = session.scalar(
                select(RagEvaluationRun).where(RagEvaluationRun.id == object_id).with_for_update()
            )
            target: RagIndexVersion | RagEvaluationRun | None = evaluation
        else:
            target = row
        if target is None:
            return {"id": object_id, "status": "missing"}
        if target.status in {"succeeded", "failed"}:
            return {"id": object_id, "status": target.status}
        try:
            target.status = "running"
            session.commit()
            # Reacquire after making running visible. A duplicate worker waits here;
            # a killed worker leaves recoverable running state and no partial output.
            model = type(target)
            locked_target = session.scalar(
                select(model)
                .where(model.id == object_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            assert isinstance(locked_target, (RagIndexVersion, RagEvaluationRun))
            target = locked_target
            if target.status in {"succeeded", "failed"}:
                return {"id": object_id, "status": target.status}
            if isinstance(target, RagIndexVersion):
                rag.build_index(session, load_settings(), target)
            else:
                rag.evaluate(session, target)
            session.commit()
            return {"id": object_id, "status": "succeeded"}
        except Exception as exc:
            session.rollback()
            code = (
                str(exc) if isinstance(exc, (rag.RagError, ValueError)) else "RAG_EXECUTION_ERROR"
            )
            safe = code if code.isupper() and len(code) <= 100 else "RAG_EXECUTION_ERROR"
            retries = int(getattr(getattr(self, "request", None), "retries", 0))
            if safe in {"ADAPTER_UNAVAILABLE", "RAG_EXECUTION_ERROR"} and retries < 3:
                raise self.retry(exc=RuntimeError(safe), countdown=2**retries) from None
            failed_target = session.get(type(target), object_id)
            if isinstance(failed_target, (RagIndexVersion, RagEvaluationRun)):
                failed_target.status = "failed"
                failed_target.error_code = safe
                session.commit()
            return {"id": object_id, "status": "failed", "error_code": safe}


@celery_app.task(bind=True, name="corpusflow.collect", max_retries=2, acks_late=True)  # type: ignore[untyped-decorator]
def collect(self: Any, plan_id: str) -> dict[str, str]:
    from corpusflow.db.models import IngestPlan
    from corpusflow.services import acquisition

    with _session()() as session:
        row = session.scalar(select(IngestPlan).where(IngestPlan.id == plan_id).with_for_update())
        if row is None:
            return {"plan_id": plan_id, "status": "missing"}
        if row.status not in {"queued", "running"}:
            return {"plan_id": plan_id, "status": row.status}
        try:
            # Single transaction: no partially registered successful plan. Object
            # writes are conditional and content-addressed; retries cannot overwrite.
            row.status = "running"
            session.commit()
            session.refresh(row, with_for_update=True)
            if row.status not in {"queued", "running"}:
                return {"plan_id": plan_id, "status": row.status}
            acquisition.execute(session, load_settings(), row)
            session.commit()
            return {"plan_id": plan_id, "status": "succeeded"}
        except Exception as exc:
            session.rollback()
            code = str(exc) if isinstance(exc, ValueError) else "ACQUISITION_EXECUTION_FAILED"
            if not code.isupper() or len(code) > 100:
                code = "ACQUISITION_EXECUTION_FAILED"
            if (
                code in {"ACQUISITION_NETWORK_FAILED", "ACQUISITION_EXECUTION_FAILED"}
                and self.request.retries < 2
            ):
                raise self.retry(exc=RuntimeError(code), countdown=2) from None
            row = session.get(IngestPlan, plan_id)
            assert row is not None
            row.status = "failed"
            row.error_code = code
            session.commit()
            return {"plan_id": plan_id, "status": "failed", "error_code": code}


@celery_app.task(bind=True, name="corpusflow.generate", max_retries=20, acks_late=True)  # type: ignore[untyped-decorator]
def generate(self: Any, generation_id: str) -> dict[str, str]:
    from sqlalchemy import text

    from corpusflow.db.models import GenerationRun
    from corpusflow.services import generation

    settings = load_settings()
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            # Session-level lock pins one connection through reservation commits.
            # Serial provider calls bound concurrency without retrying HTTP requests.
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtext('cf-generation-provider'))")
            )
            connection.commit()
            if not acquired:
                raise self.retry(exc=RuntimeError("GENERATION_PROVIDER_BUSY"), countdown=5)
            try:
                with Session(bind=connection, expire_on_commit=False) as session:
                    row = session.get(GenerationRun, generation_id)
                    if row is None:
                        return {"id": generation_id, "status": "missing"}
                    if row.status in {"succeeded", "refused", "failed"}:
                        return {"id": row.id, "status": row.status}
                    try:
                        if row.call_reserved:
                            raise ValueError("GENERATION_CALL_OUTCOME_UNKNOWN")
                        generation.execute(session, settings, row)
                        session.commit()
                    except Exception as exc:
                        session.rollback()
                        code = str(exc) if isinstance(exc, ValueError) else "GENERATION_FAILED"
                        if not code.isupper() or len(code) > 100:
                            code = "GENERATION_FAILED"
                        row = session.get(GenerationRun, generation_id)
                        assert row is not None
                        row.status = "failed"
                        row.error_code = code
                        session.commit()
                    return {"id": row.id, "status": row.status}
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtext('cf-generation-provider'))")
                )
                connection.commit()
    finally:
        engine.dispose()
