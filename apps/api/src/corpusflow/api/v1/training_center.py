"""Authenticated catalog reads, registered by create_app."""

from __future__ import annotations

from collections.abc import Iterator
from threading import Lock
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from corpusflow.api.dependencies import actor_id, db, workspace_id
from corpusflow.contracts.training_center import models as m
from corpusflow.core.config import Settings
from corpusflow.core.errors import ErrorResponse
from corpusflow.modules.training_center.catalog import CatalogError, GeneratedCatalog
from corpusflow.modules.training_center.downloads import (
    authorize_export,
    chunks,
    prepare_export,
    stored_manifest,
)
from corpusflow.modules.training_center.query import CatalogQueries
from corpusflow.modules.training_center.workspace import (
    WorkspaceCatalogProvider,
    WorkspaceSnapshots,
)

router = APIRouter(
    prefix="/api/v1/training-center",
    tags=["training-center"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 413, 422, 503)},
)
bearer = HTTPBearer(auto_error=False, scheme_name="TrainingCenterBearer")
_store_lock = Lock()


def authorized_workspace(
    request: Request,
    session: Annotated[Session, Depends(db)],
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    _workspace: Annotated[
        str | None,
        Header(
            alias="X-Workspace-ID",
            description=(
                "Authorized workspace. If omitted, retain the existing "
                "first active membership policy."
            ),
        ),
    ] = None,
) -> str:
    # Header/security declarations document the existing policy; they do not replace it.
    return workspace_id(request, session, actor_id(request, session))


def catalog_store(request: Request) -> GeneratedCatalog:
    # Process-local decoded cache; auth runs on EVERY request, including warm-cache reads.
    with _store_lock:
        store = getattr(request.app.state, "training_center_generated", None)
        if not isinstance(store, GeneratedCatalog):
            settings: Settings = request.app.state.config
            store = GeneratedCatalog(
                settings.training_center_data_dir,
                settings.training_center_max_records,
                settings.training_center_max_bytes,
            )
            request.app.state.training_center_generated = store
        return store


class Reader:
    def __init__(
        self,
        store: GeneratedCatalog,
        workspace: str,
        session: Session,
        request: Request,
        workspace_provider: WorkspaceCatalogProvider,
    ) -> None:
        self.store = store
        self.workspace = workspace
        self.session = session
        self.request = request
        self.settings: Settings = request.app.state.config
        self.workspace_provider = workspace_provider

    def query(self, params: m.CatalogQuery) -> CatalogQueries:
        if params.catalog == "workspace":
            return CatalogQueries(
                self.workspace_provider.load(
                    self.workspace,
                    params.revision,
                    self.session,
                    self.settings.training_center_max_records,
                    self.settings.training_center_max_bytes,
                )
            )
        return CatalogQueries(self.store.load(self.workspace, params.revision))


def workspace_store(request: Request) -> WorkspaceCatalogProvider:
    """Agent 1 can override this dependency without changing catalog consumers."""
    with _store_lock:
        cache = getattr(request.app.state, "training_center_workspace", None)
        if cache is None:
            settings: Settings = request.app.state.config
            cache = WorkspaceSnapshots(
                settings.training_center_snapshot_ttl_seconds,
                settings.training_center_snapshot_max_per_workspace,
            )
            request.app.state.training_center_workspace = cache
        return cast(WorkspaceCatalogProvider, cache)


def reader(
    request: Request,
    workspace: Annotated[str, Depends(authorized_workspace)],
    store: Annotated[GeneratedCatalog, Depends(catalog_store)],
    session: Annotated[Session, Depends(db)],
    workspace_provider: Annotated[WorkspaceCatalogProvider, Depends(workspace_store)],
) -> Iterator[Reader]:
    try:
        yield Reader(store, workspace, session, request, workspace_provider)
    except CatalogError as exc:
        raise HTTPException(exc.status, exc.code) from None


Read = Annotated[Reader, Depends(reader)]


@router.get("/overview", response_model=m.OverviewResponse)
def overview(read: Read, query: Annotated[m.CatalogQuery, Query()]) -> m.OverviewResponse:
    return read.query(query).overview()


@router.get("/formats/{format}/stats", response_model=m.FormatStatsResponse)
def stats(
    format: m.FileFormat | Literal["all"], read: Read, query: Annotated[m.StatsQuery, Query()]
) -> m.FormatStatsResponse:
    return read.query(query).stats(format, query)


@router.get("/files", response_model=m.FilesResponse)
def files(read: Read, query: Annotated[m.FilesQuery, Query()]) -> m.FilesResponse:
    return read.query(query).files(query)


@router.get("/files/{file_id}", response_model=m.FileDetailResponse)
def file_detail(
    file_id: str, read: Read, query: Annotated[m.CatalogQuery, Query()]
) -> m.FileDetailResponse:
    return read.query(query).file(file_id)


@router.get("/files/{file_id}/comparison", response_model=m.ComparisonResponse)
def comparison(
    file_id: str, read: Read, query: Annotated[m.ComparisonQuery, Query()]
) -> m.ComparisonResponse:
    read.query(query).file(file_id)  # Check object visibility before reporting missing processing.
    raise HTTPException(404, "COMPARISON_NOT_AVAILABLE")


@router.get("/datasets", response_model=m.DatasetsResponse)
def datasets(read: Read, query: Annotated[m.DatasetsQuery, Query()]) -> m.DatasetsResponse:
    return read.query(query).datasets(query.kind)


@router.get("/datasets/{dataset_id}/overview", response_model=m.DatasetOverviewResponse)
def dataset_overview(
    dataset_id: str, read: Read, query: Annotated[m.DatasetQuery, Query()]
) -> m.DatasetOverviewResponse:
    return read.query(query).dataset_overview(dataset_id, query.version)


@router.get("/datasets/{dataset_id}/samples", response_model=m.SamplesResponse)
def samples(
    dataset_id: str, read: Read, query: Annotated[m.SamplesQuery, Query()]
) -> m.SamplesResponse:
    return read.query(query).samples(dataset_id, query)


@router.get("/datasets/{dataset_id}/samples/{sample_id}", response_model=m.SamplesResponse)
def sample_detail(
    dataset_id: str, sample_id: str, read: Read, query: Annotated[m.DatasetQuery, Query()]
) -> m.SamplesResponse:
    return read.query(query).sample(dataset_id, query.version, sample_id)


@router.get("/datasets/{dataset_id}/manifest", response_model=m.ManifestResponse)
def manifest(
    dataset_id: str, read: Read, query: Annotated[m.DatasetQuery, Query()]
) -> m.ManifestResponse:
    queries = read.query(query)
    if query.catalog == "workspace":
        return stored_manifest(
            queries.snapshot, queries._dataset(dataset_id, query.version), read.settings
        )
    return queries.manifest(dataset_id, query.version)


@router.get(
    "/datasets/{dataset_id}/export",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Complete filtered version download (UTF-8)",
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in ("application/x-ndjson", "text/markdown", "text/csv", "text/plain")
            },
        }
    },
)
def export(
    dataset_id: str,
    read: Read,
    request: Request,
    query: Annotated[m.ExportQuery, Depends()],
    q: Annotated[
        str | None, Query(description="Same text search as samples; export every matching record")
    ] = None,
) -> StreamingResponse:
    from corpusflow.api.v1.business import audit

    # Additive q parameter until Agent 1 updates the canonical ExportQuery.
    # Keep strict rejection of accidental page-only export arguments.
    unknown = set(request.query_params) - set(m.ExportQuery.model_fields) - {"q"}
    if unknown:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", name),
                    "msg": "Extra inputs are not permitted",
                    "type": "extra_forbidden",
                    "input": request.query_params[name],
                }
                for name in sorted(unknown)
            ]
        )
    queries = read.query(query)
    dataset = queries._dataset(dataset_id, query.version)
    authorize_export(read.session, queries.snapshot, dataset)
    samples = queries.filtered_samples(
        dataset_id, m.SamplesQuery(version=query.version, split=query.split, q=q)
    )
    stream, content_type, disposition, size = prepare_export(
        samples,
        dataset,
        query.export_format,
        read.settings.training_center_max_records,
        read.settings.training_center_max_bytes,
    )
    try:
        audit(
            read.session,
            read.request,
            read.workspace,
            actor_id(read.request, read.session),
            "training_center.dataset.export",
            "dataset_version",
            dataset.version_id,
            {
                "catalog": query.catalog,
                "revision": queries.scope.revision,
                "split": query.split,
                "q": q,
                "purpose": "training",
                "export_format": query.export_format,
                "record_count": len(samples),
            },
        )
        read.session.commit()
    except Exception:
        stream.close()
        raise
    return StreamingResponse(
        chunks(stream),
        media_type=content_type
        if "charset=" in content_type.lower()
        else f"{content_type}; charset=utf-8",
        headers={"Content-Disposition": disposition, "Content-Length": str(size)},
        background=BackgroundTask(stream.close),
    )
