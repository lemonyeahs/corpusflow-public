"""Bounded manifest reads and caller-side export policy; serialization belongs to Agent 3."""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Iterator
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Protocol, cast
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.adapters.storage import S3ObjectStore
from corpusflow.contracts.training_center import models as m
from corpusflow.core.config import Settings
from corpusflow.db.models import DatasetVersion, LicenseGrant
from corpusflow.modules.training_center.catalog import CatalogError, CatalogSnapshot, decode_json
from corpusflow.modules.training_center.generation import Json, json_bytes, sha256


def stored_manifest(
    snapshot: CatalogSnapshot, dataset: m.DatasetSummary, settings: Settings
) -> m.ManifestResponse:
    metadata = snapshot.version_metadata[dataset.version_id]
    storage = S3ObjectStore(
        settings.object_store_endpoint,
        settings.object_store_bucket,
        settings.object_store_access_key.get_secret_value(),
        settings.object_store_secret_key.get_secret_value(),
    )
    client = storage._client()
    try:
        response = client.get_object(Bucket=storage.bucket, Key=metadata["manifest_storage_key"])
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > settings.training_center_max_bytes:
                raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
            content = body.read(settings.training_center_max_bytes + 1)
        finally:
            body.close()
        if len(content) > settings.training_center_max_bytes:
            raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
        if sha256(content) != metadata["manifest_sha256"]:
            raise CatalogError("CHECKSUM_MISMATCH", 409)
        manifest = decode_json(content)
        if not isinstance(manifest, dict):
            raise CatalogError("CHECKSUM_MISMATCH", 409)
        return m.ManifestResponse(
            scope=snapshot.scope,
            dataset_id=dataset.id,
            version=dataset.version,
            manifest=manifest,
            content_hash=sha256(json_bytes(manifest)),
        )
    except CatalogError:
        raise
    except Exception as exc:
        raise CatalogError("ADAPTER_UNAVAILABLE", 503) from exc
    finally:
        client.close()


def authorize_export(
    session: Session, snapshot: CatalogSnapshot, dataset: m.DatasetSummary
) -> None:
    if snapshot.scope.catalog == "generated":
        return
    # Recheck live publication and grants on EVERY download, including an old snapshot.
    version = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == dataset.version_id,
            DatasetVersion.workspace_id == snapshot.scope.workspace_id,
            DatasetVersion.status == "published",
        )
    )
    if version is None:
        raise CatalogError("NOT_FOUND", 404)
    files: set[str] = set()
    for sample in snapshot.samples:
        if (sample.dataset_id, sample.dataset_version) == (dataset.id, dataset.version):
            evidence = snapshot.sample_files.get(
                (sample.dataset_id, sample.dataset_version, sample.id), set()
            )
            if not evidence:
                raise CatalogError("DOWNLOAD_NOT_AUTHORIZED", 403)
            files.update(evidence)
    if not files:
        raise CatalogError("DOWNLOAD_NOT_AUTHORIZED", 403)
    allowed = set(
        session.scalars(
            select(LicenseGrant.asset_id).where(
                LicenseGrant.workspace_id == snapshot.scope.workspace_id,
                LicenseGrant.asset_id.in_(files),
                LicenseGrant.purpose == "training",
                LicenseGrant.status == "confirmed",
            )
        )
    )
    if files != allowed:
        raise CatalogError("DOWNLOAD_NOT_AUTHORIZED", 403)


class SerializedExport(Protocol):
    chunks: Iterator[bytes]
    content_type: str
    extension: str


def serializer(records: Iterable[Json], kind: str, export_format: str) -> SerializedExport:
    """Late binding lets DB/UI reads run before Agent 3 delivers the shared serializer."""
    try:
        module = importlib.import_module("corpusflow.services.processing_exports")
        return cast(SerializedExport, module.serialize_records(records, kind, export_format))
    except (ImportError, AttributeError) as exc:
        raise CatalogError("ADAPTER_UNAVAILABLE", 503) from exc


def prepare_export(
    samples: list[m.Sample],
    dataset: m.DatasetSummary,
    export_format: str,
    max_records: int,
    max_bytes: int,
) -> tuple[BinaryIO, str, str, int]:
    if len(samples) > max_records:
        raise CatalogError("EXPORT_LIMIT_EXCEEDED", 413)
    serialized = serializer((s.model_dump() for s in samples), dataset.kind, export_format)
    extensions = {"jsonl": "jsonl", "markdown": "md", "csv": "csv", "txt": "txt"}
    if serialized.extension.lstrip(".") != extensions[export_format]:
        raise CatalogError("ADAPTER_UNAVAILABLE", 503)
    output = cast(BinaryIO, SpooledTemporaryFile(max_size=min(max_bytes, 1024 * 1024), mode="w+b"))
    size = 0
    try:
        for chunk in serialized.chunks:
            size += len(chunk)
            if size > max_bytes:
                raise CatalogError("EXPORT_LIMIT_EXCEEDED", 413)
            output.write(chunk)
        output.seek(0)
        filename = f"{dataset.name}-{dataset.version}.{extensions[export_format]}"
        disposition = (
            f"attachment; filename=dataset.{extensions[export_format]}; "
            f"filename*=UTF-8''{quote(filename, safe='')}"
        )
        return output, serialized.content_type, disposition, size
    except Exception:
        output.close()
        raise


def chunks(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while data := stream.read(64 * 1024):
            yield data
    finally:
        stream.close()
