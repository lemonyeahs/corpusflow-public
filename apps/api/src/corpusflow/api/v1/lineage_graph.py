"""Multi-hop lineage reads from the same frozen workspace as catalog and processing."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from corpusflow.api.v1.training_center import Read
from corpusflow.contracts.training_center.models import GraphQuery, LineageGraph, ObjectRef
from corpusflow.services.training_center_graph import (
    _generated_node_details,
    _generated_projection,
    _stored_graph,
)

router = APIRouter(prefix="/api/v1", tags=["training-center-lineage"])


@router.get("/lineage/graph", response_model=LineageGraph)
def graph(read: Read, query: Annotated[GraphQuery, Query()]) -> LineageGraph:
    snapshot = read.query(query).snapshot
    root = ObjectRef(catalog=query.catalog, type=query.root_type, id=query.root_id)
    if query.catalog == "generated":
        rows, visible = _generated_projection(snapshot)
        details = _generated_node_details(snapshot)
    else:
        if snapshot.graph is None:
            raise HTTPException(409, "SNAPSHOT_EXPIRED")
        rows, visible = snapshot.graph.rows, snapshot.graph.visible
        details = dict(snapshot.graph.node_details)
    return _stored_graph(
        rows,
        query.catalog,
        read.workspace,
        root,
        query,
        revision=snapshot.scope.revision,
        as_of=snapshot.scope.as_of,
        visible=visible,
        node_details=details,
    )
