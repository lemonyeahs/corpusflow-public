"""Multi-hop lineage traversal independent of SQLAlchemy and HTTP concerns."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["both", "upstream", "downstream"]

DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_NODES = 200
MAX_DEPTH = 12
MAX_NODES = 500


class GraphQueryError(ValueError):
    """Raised when a graph query is invalid or its root is not visible."""


@dataclass(frozen=True, order=True)
class GraphNode:
    kind: str
    id: str
    label: str | None = None
    status: str | None = None
    detail: Mapping[str, object] = field(default_factory=dict, compare=False)

    @property
    def key(self) -> tuple[str, str]:
        return self.kind, self.id


@dataclass(frozen=True, order=True)
class GraphEdge:
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    relation: str

    @property
    def source(self) -> tuple[str, str]:
        return self.source_kind, self.source_id

    @property
    def target(self) -> tuple[str, str]:
        return self.target_kind, self.target_id


@dataclass(frozen=True)
class GraphResult:
    root: GraphNode
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    truncated: bool = False
    truncation_reason: Literal["max_depth", "max_nodes"] | None = None

    @property
    def node_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(node.key for node in self.nodes)


def _validate_query(direction: str, max_depth: int, max_nodes: int) -> tuple[Direction, int, int]:
    if direction not in {"both", "upstream", "downstream"}:
        raise GraphQueryError("direction must be one of both, upstream, downstream")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int):
        raise GraphQueryError("max_depth must be an integer")
    if max_depth < 0 or max_depth > MAX_DEPTH:
        raise GraphQueryError(f"max_depth must be between 0 and {MAX_DEPTH}")
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int):
        raise GraphQueryError("max_nodes must be an integer")
    if max_nodes < 1 or max_nodes > MAX_NODES:
        raise GraphQueryError(f"max_nodes must be between 1 and {MAX_NODES}")
    return direction, max_depth, max_nodes


def _coerce_node(value: GraphNode | Mapping[str, object]) -> GraphNode:
    if isinstance(value, GraphNode):
        return value
    try:
        kind = str(value["kind"])
        node_id = str(value["id"])
    except (KeyError, TypeError) as exc:
        raise GraphQueryError("node must contain kind and id") from exc
    if not kind or not node_id:
        raise GraphQueryError("node kind and id cannot be empty")
    return GraphNode(
        kind=kind,
        id=node_id,
        label=str(value.get("label")) if value.get("label") is not None else None,
        status=str(value.get("status")) if value.get("status") is not None else None,
        detail=value.get("detail", {}) if isinstance(value.get("detail", {}), Mapping) else {},
    )


def _coerce_edge(value: GraphEdge | Mapping[str, object]) -> GraphEdge:
    if isinstance(value, GraphEdge):
        return value
    # Accept both the storage names and the contract's source/target shape.
    try:
        source_kind = value.get("source_kind", value.get("from_type"))
        source_id = value.get("source_id", value.get("from_id"))
        target_kind = value.get("target_kind", value.get("to_type"))
        target_id = value.get("target_id", value.get("to_id"))
        relation = value["relation"]
    except (KeyError, TypeError) as exc:
        raise GraphQueryError("edge must contain source, target and relation") from exc
    values = (source_kind, source_id, target_kind, target_id, relation)
    if any(item is None or str(item) == "" for item in values):
        raise GraphQueryError("edge source, target and relation cannot be empty")
    return GraphEdge(*(str(item) for item in values))


def query_graph(
    edges: Iterable[GraphEdge | Mapping[str, object]],
    root: GraphNode | Mapping[str, object] | tuple[str, str],
    *,
    direction: Direction = "both",
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    nodes: Iterable[GraphNode | Mapping[str, object]] | None = None,
) -> GraphResult:
    """Return a bounded, de-duplicated graph rooted at ``root``.

    ``source`` always means upstream and ``target`` always means downstream.
    For ``upstream`` traversal only incoming edges are followed; the returned
    edge orientation remains source-to-target. ``nodes`` is an optional visible
    node registry. When provided, edges with a missing endpoint are ignored so
    a dangling database row can never leak into the response.
    """

    direction, max_depth, max_nodes = _validate_query(direction, max_depth, max_nodes)
    if isinstance(root, tuple):
        if len(root) != 2 or not all(str(item) for item in root):
            raise GraphQueryError("root must contain type and id")
        root_node = GraphNode(str(root[0]), str(root[1]))
    else:
        root_node = _coerce_node(root)

    visible: dict[tuple[str, str], GraphNode] = {}
    if nodes is not None:
        for value in nodes:
            node = _coerce_node(value)
            visible.setdefault(node.key, node)
        if root_node.key not in visible:
            raise GraphQueryError("root node not found")
    else:
        visible[root_node.key] = root_node

    unique_edges: dict[tuple[str, str, str, str, str], GraphEdge] = {}
    for value in edges:
        edge = _coerce_edge(value)
        if nodes is not None and (edge.source not in visible or edge.target not in visible):
            continue
        unique_edges[
            (
                edge.source_kind,
                edge.source_id,
                edge.target_kind,
                edge.target_id,
                edge.relation,
            )
        ] = edge
        if edge.source not in visible:
            visible[edge.source] = GraphNode(*edge.source)
        if edge.target not in visible:
            visible[edge.target] = GraphNode(*edge.target)

    outgoing: dict[tuple[str, str], list[GraphEdge]] = defaultdict(list)
    incoming: dict[tuple[str, str], list[GraphEdge]] = defaultdict(list)
    for edge in sorted(unique_edges.values()):
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

    selected: dict[tuple[str, str], GraphNode] = {root_node.key: visible[root_node.key]}
    selected_edges: dict[tuple[str, str, str, str, str], GraphEdge] = {}
    queue: deque[tuple[tuple[str, str], int]] = deque([(root_node.key, 0)])
    truncated_reason: Literal["max_depth", "max_nodes"] | None = None

    while queue:
        current, depth = queue.popleft()
        candidates: list[tuple[GraphEdge, tuple[str, str]]] = []
        if direction in {"both", "downstream"}:
            candidates.extend((edge, edge.target) for edge in outgoing[current])
        if direction in {"both", "upstream"}:
            candidates.extend((edge, edge.source) for edge in incoming[current])
        for edge, neighbour in sorted(candidates, key=lambda item: item[0]):
            edge_key = (
                edge.source_kind,
                edge.source_id,
                edge.target_kind,
                edge.target_id,
                edge.relation,
            )
            if neighbour in selected:
                if edge_key not in selected_edges and depth < max_depth:
                    selected_edges[edge_key] = edge
                continue
            if depth >= max_depth:
                truncated_reason = "max_depth"
                continue
            if len(selected) >= max_nodes:
                truncated_reason = "max_nodes"
                continue
            selected[neighbour] = visible[neighbour]
            selected_edges[edge_key] = edge
            queue.append((neighbour, depth + 1))

    result_nodes = tuple(sorted(selected.values(), key=lambda node: node.key))
    result_edges = tuple(
        edge
        for edge in sorted(selected_edges.values())
        if edge.source in selected and edge.target in selected
    )
    return GraphResult(
        root=selected[root_node.key],
        nodes=result_nodes,
        edges=result_edges,
        truncated=truncated_reason is not None,
        truncation_reason=truncated_reason,
    )
