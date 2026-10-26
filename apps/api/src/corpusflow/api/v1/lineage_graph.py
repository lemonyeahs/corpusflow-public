"""V1 multi-hop lineage graph endpoint for workspace lineage rows."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.api.dependencies import actor_id, db, workspace_id
from corpusflow.contracts.training_center.models import (
    GraphQuery,
    LineageGraph,
    LineageNode,
    ObjectRef,
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

STORAGE_TYPES = {
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
RELATIONS = {
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
WORKSPACE_MODELS = {
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
    rows: list[StoredLineageEdge],
    catalog: str,
    workspace: str,
    root: ObjectRef,
    query: GraphQuery,
) -> LineageGraph:
    graph_edges: list[GraphEdge] = []
    nodes: dict[tuple[str, str], GraphNode] = {}
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
        node.key: ObjectRef(catalog=catalog, type=node.kind, id=node.id)
        for node in result.nodes
    }
    wire_nodes = [
        LineageNode(
            id=_node_id(catalog, node.kind, node.id),
            ref=refs[node.key],
            kind=node.kind,
            label=node.label or node.id,
            description=f"{node.kind} 节点 {node.id}",
            status=node.status,
            metrics={},
            detail=dict(node.detail),
        )
        for node in result.nodes
    ]
    wire_edges = [
        WireLineageEdge(
            id=_edge_id(edge, catalog),
            source=_node_id(catalog, edge.source_kind, edge.source_id),
            target=_node_id(catalog, edge.target_kind, edge.target_id),
            relation=edge.relation,
        )
        for edge in result.edges
    ]
    return LineageGraph(
        scope=Scope(
            workspace_id=workspace,
            catalog=catalog,
            revision=query.revision or "workspace-live",
            as_of=_now(),
            metric_definition_version="1.0.0",
        ),
        root=root,
        nodes=wire_nodes,
        edges=wire_edges,
        truncated=result.truncated,
        truncation_reason=result.truncation_reason,
    )


def _workspace_nodes(session: Session, workspace: str) -> dict[str, set[str]]:
    return {
        storage_type: set(session.scalars(select(model.id).where(model.workspace_id == workspace)))
        for storage_type, model in WORKSPACE_MODELS.items()
    }


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
    rows = [
        row
        for row in rows
        if row.from_type in visible
        and row.to_type in visible
        and row.from_id in visible[row.from_type]
        and row.to_id in visible[row.to_type]
    ]
    root = ObjectRef(catalog=query.catalog, type=query.root_type, id=query.root_id)
    return _stored_graph(rows, query.catalog, workspace, root, query)
