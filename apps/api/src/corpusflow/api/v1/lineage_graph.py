"""V1 multi-hop lineage graph endpoint for workspace lineage rows."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.api.dependencies import actor_id, db, workspace_id
from corpusflow.contracts.training_center.models import (
    Catalog,
    GraphQuery,
    LineageGraph,
    LineageNode,
    ObjectRef,
    ObjectType,
    Scope,
)
from corpusflow.contracts.training_center.models import (
    LineageEdge as WireLineageEdge,
)
from corpusflow.db.models import (
    Asset,
    CandidateSample,
    DatasetVersion,
    DocumentVersion,
    PipelineRun,
    PreferenceSample,
    Segment,
    Source,
)
from corpusflow.db.models import (
    LineageEdge as StoredLineageEdge,
)
from corpusflow.modules.lineage_graph import GraphEdge, GraphNode, query_graph

router = APIRouter(prefix="/api/v1", tags=["training-center-lineage"])

STORAGE_TYPES: dict[str, ObjectType] = {
    "Source": "source",
    "Asset": "file",
    "DocumentVersion": "file",
    "PipelineRun": "operator_run",
    "NodeRun": "operator_run",
    "Segment": "segment",
    "CandidateSample": "sample",
    "PreferenceSample": "sample",
    "DatasetVersion": "dataset_version",
}


@dataclass(frozen=True)
class FrozenEdge:
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    relation: str


@dataclass(frozen=True)
class GraphSnapshot:
    revision: str
    as_of: str
    expires_at: float
    rows: tuple[FrozenEdge, ...]
    visible: frozenset[tuple[str, str]]


class GraphSnapshots:
    """App-local workspace snapshots; restart expires them, reads never renew TTL.

    Multi-process deployments must use shared storage or sticky snapshot routing.
    Only immutable projections are retained, never ORM instances or sessions.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = RLock()
        self._workspaces: dict[str, OrderedDict[str, GraphSnapshot]] = {}

    def _expire(self, now: float) -> None:
        for workspace, snapshots in list(self._workspaces.items()):
            for revision, snapshot in list(snapshots.items()):
                if snapshot.expires_at <= now:
                    del snapshots[revision]
            if not snapshots:
                del self._workspaces[workspace]

    def get(self, workspace: str, revision: str) -> GraphSnapshot:
        with self._lock:
            self._expire(self._clock())
            snapshots = self._workspaces.get(workspace)
            snapshot = snapshots.get(revision) if snapshots is not None else None
            if snapshot is None:
                raise HTTPException(409, "SNAPSHOT_EXPIRED")
            return snapshot

    def put(
        self,
        workspace: str,
        rows: tuple[FrozenEdge, ...],
        visible: frozenset[tuple[str, str]],
    ) -> GraphSnapshot:
        with self._lock:
            now = self._clock()
            self._expire(now)
            snapshot = GraphSnapshot(uuid.uuid4().hex, _now(), now + 900, rows, visible)
            snapshots = self._workspaces.setdefault(workspace, OrderedDict())
            snapshots[snapshot.revision] = snapshot
            while len(snapshots) > 10:
                snapshots.popitem(last=False)
            return snapshot


_STORE_LOCK = RLock()


def _snapshots(request: Request) -> GraphSnapshots:
    with _STORE_LOCK:
        store = getattr(request.app.state, "lineage_snapshots", None)
        if not isinstance(store, GraphSnapshots):
            store = GraphSnapshots()
            request.app.state.lineage_snapshots = store
        return store


RELATIONS = {
    "provides": "provides",
    "parsed_by": "parsed_by",
    "contains": "provides",
    "contributed_to": "provides",
    "acquired": "provides",
    "registered": "provides",
    "parsed_to": "parsed_by",
    "transformed_to": "derived_from",
    "transformed_segment": "derived_from",
    "contained_in": "derived_from",
    "reprocessed_equivalent": "derived_from",
    "materialized_in": "included_in",
    "published_as": "produced",
    "processed_by": "processed_by",
    "produced": "produced",
    "included_in": "included_in",
    "split_into": "split_into",
    "derived_from": "derived_from",
}
WORKSPACE_MODELS: dict[
    str,
    type[Source]
    | type[Asset]
    | type[DocumentVersion]
    | type[PipelineRun]
    | type[Segment]
    | type[CandidateSample]
    | type[PreferenceSample]
    | type[DatasetVersion],
] = {
    "Source": Source,
    "Asset": Asset,
    "DocumentVersion": DocumentVersion,
    "PipelineRun": PipelineRun,
    "Segment": Segment,
    "CandidateSample": CandidateSample,
    "PreferenceSample": PreferenceSample,
    "DatasetVersion": DatasetVersion,
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _node_id(catalog: str, kind: str, value: str) -> str:
    return f"{catalog}:{kind}:{value}"


def _edge_id(edge: GraphEdge, catalog: str) -> str:
    raw = "|".join(
        (catalog, edge.source_kind, edge.source_id, edge.target_kind, edge.target_id, edge.relation)
    )
    return "edge-" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _stored_graph(
    rows: Sequence[StoredLineageEdge | FrozenEdge],
    catalog: Catalog,
    workspace: str,
    root: ObjectRef,
    query: GraphQuery,
    *,
    revision: str,
    as_of: str,
    visible: frozenset[tuple[str, str]] = frozenset(),
) -> LineageGraph:
    graph_edges: list[GraphEdge] = []
    nodes: dict[tuple[str, str], GraphNode] = {}
    for storage_type, value in sorted(visible):
        kind = STORAGE_TYPES.get(storage_type)
        if kind:
            nodes.setdefault(
                (kind, value),
                GraphNode(
                    kind, value, f"{kind}:{value[:12]}", detail={"storage_kind": storage_type}
                ),
            )
    for row in rows:
        source_kind = STORAGE_TYPES.get(row.from_type)
        target_kind = STORAGE_TYPES.get(row.to_type)
        relation = RELATIONS.get(row.relation, "derived_from")
        if not source_kind or not target_kind:
            continue
        edge = GraphEdge(source_kind, row.from_id, target_kind, row.to_id, relation)
        graph_edges.append(edge)
        nodes.setdefault(
            edge.source,
            GraphNode(
                edge.source_kind,
                edge.source_id,
                f"{edge.source_kind}:{edge.source_id[:12]}",
                detail={"storage_kind": row.from_type},
            ),
        )
        nodes.setdefault(
            edge.target,
            GraphNode(
                edge.target_kind,
                edge.target_id,
                f"{edge.target_kind}:{edge.target_id[:12]}",
                detail={"storage_kind": row.to_type},
            ),
        )
    root_key = (query.root_type, query.root_id)
    if root_key not in nodes:
        raise HTTPException(404, "NOT_FOUND")
    result = query_graph(
        graph_edges,
        root_key,
        direction=query.direction,
        max_depth=query.max_depth,
        max_nodes=query.max_nodes,
        nodes=nodes.values(),
    )

    refs = {
        node.key: ObjectRef(catalog=catalog, type=cast(ObjectType, node.kind), id=node.id)
        for node in result.nodes
    }
    wire_nodes = [
        LineageNode(
            id=_node_id(catalog, node.kind, node.id),
            ref=refs[node.key],
            kind=cast(ObjectType, node.kind),
            label=node.label or node.id,
            description=f"{node.kind} 节点 {node.id}",
            status=node.status,
            metrics={},
            detail=dict(node.detail),
        )
        for node in result.nodes
    ]
    wire_edges = [
        WireLineageEdge.model_validate(
            {
                "id": _edge_id(edge, catalog),
                "source": _node_id(catalog, edge.source_kind, edge.source_id),
                "target": _node_id(catalog, edge.target_kind, edge.target_id),
                "relation": edge.relation,
            }
        )
        for edge in result.edges
    ]
    return LineageGraph(
        scope=Scope(
            workspace_id=workspace,
            catalog=catalog,
            revision=revision,
            as_of=as_of,
            metric_definition_version="1.0.0",
        ),
        root=root,
        nodes=wire_nodes,
        edges=wire_edges,
        truncated=result.truncated,
        truncation_reason=result.truncation_reason,
    )


def _workspace_nodes(session: Session, workspace: str) -> frozenset[tuple[str, str]]:
    return frozenset(
        (storage_type, value)
        for storage_type, model in WORKSPACE_MODELS.items()
        for value in session.scalars(select(model.id).where(model.workspace_id == workspace))
    )


@router.get("/lineage/graph", response_model=LineageGraph)
def graph(
    request: Request,
    query: Annotated[GraphQuery, Query()],
    session: Annotated[Session, Depends(db)],
) -> LineageGraph:
    user = actor_id(request, session)
    workspace = workspace_id(request, session, user)
    if query.catalog == "generated":
        raise HTTPException(503, "CATALOG_UNAVAILABLE")
    store = _snapshots(request)
    if query.revision is not None:
        snapshot = store.get(workspace, query.revision)
    else:
        snapshot = _capture_snapshot(session, workspace, store)
    root = ObjectRef(catalog=query.catalog, type=query.root_type, id=query.root_id)
    return _stored_graph(
        snapshot.rows,
        query.catalog,
        workspace,
        root,
        query,
        revision=snapshot.revision,
        as_of=snapshot.as_of,
        visible=snapshot.visible,
    )


def _capture_snapshot(session: Session, workspace: str, store: GraphSnapshots) -> GraphSnapshot:
    rows = list(
        session.scalars(
            select(StoredLineageEdge)
            .where(StoredLineageEdge.workspace_id == workspace)
            .order_by(
                StoredLineageEdge.from_type,
                StoredLineageEdge.from_id,
                StoredLineageEdge.to_type,
                StoredLineageEdge.to_id,
            )
        ).all()
    )
    visible = _workspace_nodes(session, workspace)
    frozen_rows = tuple(
        FrozenEdge(row.from_type, row.from_id, row.to_type, row.to_id, row.relation)
        for row in rows
        if (row.from_type, row.from_id) in visible and (row.to_type, row.to_id) in visible
    )
    return store.put(workspace, frozen_rows, visible)
