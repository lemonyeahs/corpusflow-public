"""Deterministic, storage-agnostic traversal for the lineage graph.

The database adapter and HTTP router are intentionally kept outside this module.
This lets graph semantics be tested before the shared API is registered and keeps
the traversal usable for both workspace rows and generated manifest edges.
"""

from .service import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    GraphEdge,
    GraphNode,
    GraphQueryError,
    GraphResult,
    query_graph,
)

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_NODES",
    "GraphEdge",
    "GraphNode",
    "GraphQueryError",
    "GraphResult",
    "query_graph",
]
