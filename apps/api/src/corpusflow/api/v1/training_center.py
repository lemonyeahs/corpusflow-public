"""Authenticated generated-catalog reads, registered by create_app."""

from __future__ import annotations

from collections.abc import Iterator
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from corpusflow.api.dependencies import actor_id, db, workspace_id
from corpusflow.contracts.training_center import models as m
from corpusflow.core.config import Settings
from corpusflow.core.errors import ErrorResponse
from corpusflow.modules.training_center.catalog import CatalogError, GeneratedCatalog
from corpusflow.modules.training_center.query import CatalogQueries

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
    def __init__(self, store: GeneratedCatalog, workspace: str) -> None:
        self.store = store
        self.workspace = workspace

    def query(self, params: m.CatalogQuery) -> CatalogQueries:
        if params.catalog != "generated":
            raise CatalogError("ADAPTER_UNAVAILABLE", 503)
        return CatalogQueries(self.store.load(self.workspace, params.revision))


def reader(
    workspace: Annotated[str, Depends(authorized_workspace)],
    store: Annotated[GeneratedCatalog, Depends(catalog_store)],
) -> Iterator[Reader]:
    try:
        yield Reader(store, workspace)
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


@router.get("/datasets/{dataset_id}/manifest", response_model=m.ManifestResponse)
def manifest(
    dataset_id: str, read: Read, query: Annotated[m.DatasetQuery, Query()]
) -> m.ManifestResponse:
    return read.query(query).manifest(dataset_id, query.version)
