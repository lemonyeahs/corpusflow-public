"""V1 multi-hop lineage graph endpoint for workspace lineage rows."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    DatasetVersionSample,
    DocumentVersion,
    PipelineRun,
    PreferenceSample,
    Segment,
    Source,
)
from corpusflow.db.models import (
    Dataset as DatasetDefinition,
)
from corpusflow.db.models import (
    LineageEdge as StoredLineageEdge,
)
from corpusflow.modules.lineage_graph import GraphEdge, GraphNode, query_graph
from corpusflow.modules.training_center.catalog import CatalogError, CatalogSnapshot
from corpusflow.modules.training_center.processing import FrozenProcessing

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
    rows: tuple[FrozenEdge, ...]
    visible: frozenset[tuple[str, str]]
    node_details: tuple[tuple[tuple[str, str], dict[str, object]], ...] = ()


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
    node_details: dict[tuple[str, str], dict[str, object]] | None = None,
) -> LineageGraph:
    graph_edges: list[GraphEdge] = []
    nodes: dict[tuple[str, str], GraphNode] = {}
    details = node_details or {}
    for storage_type, value in sorted(visible):
        kind = STORAGE_TYPES.get(storage_type)
        if kind:
            detail = {"storage_kind": storage_type, **details.get((storage_type, value), {})}
            nodes.setdefault(
                (kind, value),
                GraphNode(
                    kind,
                    value,
                    str(detail.get("label") or f"{kind}:{value[:12]}"),
                    status=str(detail["status"]) if detail.get("status") else None,
                    detail=detail,
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
        detail = {"storage_kind": row.from_type, **details.get((row.from_type, row.from_id), {})}
        nodes.setdefault(
            edge.source,
            GraphNode(
                edge.source_kind,
                edge.source_id,
                str(detail.get("label") or f"{edge.source_kind}:{edge.source_id[:12]}"),
                status=str(detail["status"]) if detail.get("status") else None,
                detail=detail,
            ),
        )
        detail = {"storage_kind": row.to_type, **details.get((row.to_type, row.to_id), {})}
        nodes.setdefault(
            edge.target,
            GraphNode(
                edge.target_kind,
                edge.target_id,
                str(detail.get("label") or f"{edge.target_kind}:{edge.target_id[:12]}"),
                status=str(detail["status"]) if detail.get("status") else None,
                detail=detail,
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
            description=str(node.detail.get("description") or f"{node.kind} 节点 {node.id}"),
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


def _workspace_nodes(
    session: Session, workspace: str, max_records: int
) -> frozenset[tuple[str, str]]:
    return frozenset(
        (storage_type, value)
        for storage_type, model in WORKSPACE_MODELS.items()
        for value in session.scalars(
            select(model.id).where(model.workspace_id == workspace).limit(max_records + 1)
        )
    )


def _generated_projection(
    snapshot: CatalogSnapshot,
) -> tuple[tuple[FrozenEdge, ...], frozenset[tuple[str, str]]]:
    """Project only explicit generated-catalog references into graph edges.

    generated-v1 has no executed processing records. The projection therefore
    contains source/file/sample/dataset-version nodes and their persisted refs;
    it never invents operator runs or processing history.
    """
    visible: set[tuple[str, str]] = set()
    edges: set[FrozenEdge] = set()
    versions = {(dataset.id, dataset.version): dataset.version_id for dataset in snapshot.datasets}
    for source_id in snapshot.sources:
        visible.add(("Source", source_id))
    for file in snapshot.files:
        visible.add(("Asset", file.id))
        edges.add(FrozenEdge("Source", file.source_ref.id, "Asset", file.id, "provides"))
        for file_dataset in file.dataset_refs:
            edges.add(
                FrozenEdge("Asset", file.id, "DatasetVersion", file_dataset.id, "included_in")
            )
    for sample in snapshot.samples:
        version_id = versions.get((sample.dataset_id, sample.dataset_version))
        if version_id is None:
            raise HTTPException(409, "CHECKSUM_MISMATCH")
        visible.add(("CandidateSample", sample.id))
        for source_ref in sample.source_refs:
            edges.add(FrozenEdge("Source", source_ref.id, "CandidateSample", sample.id, "provides"))
        edges.add(
            FrozenEdge(
                "CandidateSample",
                sample.id,
                "DatasetVersion",
                version_id,
                "included_in",
            )
        )
    for dataset in snapshot.datasets:
        visible.add(("DatasetVersion", dataset.version_id))
        for source_ref in dataset.source_refs:
            edges.add(
                FrozenEdge(
                    "Source", source_ref.id, "DatasetVersion", dataset.version_id, "provides"
                )
            )
    return (
        tuple(
            sorted(
                edges,
                key=lambda row: (
                    row.from_type,
                    row.from_id,
                    row.to_type,
                    row.to_id,
                    row.relation,
                ),
            )
        ),
        frozenset(visible),
    )


def _generated_node_details(
    snapshot: CatalogSnapshot,
) -> dict[tuple[str, str], dict[str, object]]:
    details: dict[tuple[str, str], dict[str, object]] = {}
    for file in snapshot.files:
        details[("Asset", file.id)] = {"label": file.filename, "filename": file.filename}
    for sample in snapshot.samples:
        details[("CandidateSample", sample.id)] = {
            "dataset_id": sample.dataset_id,
            "dataset_version": sample.dataset_version,
            "dataset_kind": sample.kind,
            "label": f"{sample.kind} 样本 {sample.id[:12]}",
        }
    for dataset in snapshot.datasets:
        details[("DatasetVersion", dataset.version_id)] = {
            "dataset_id": dataset.id,
            "dataset_version": dataset.version,
            "dataset_kind": dataset.kind,
            "label": f"{dataset.name} · {dataset.version}",
        }
    return details


def _training_kind(product_type: str) -> str:
    """Map persisted product types to the training-center route kind."""
    return "cpt" if product_type == "pretrain" else product_type


def capture_graph(
    session: Session,
    workspace: str,
    scope: Scope,
    processing: dict[str, FrozenProcessing],
    max_records: int,
) -> GraphSnapshot:
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
            .limit(max_records + 1)
        ).all()
    )
    visible = _workspace_nodes(session, workspace, max_records)
    if len(rows) > max_records or len(visible) > max_records:
        raise CatalogError("CATALOG_LIMIT_EXCEEDED", 413)
    frozen_rows = [
        FrozenEdge(row.from_type, row.from_id, row.to_type, row.to_id, row.relation)
        for row in rows
        if (row.from_type, row.from_id) in visible and (row.to_type, row.to_id) in visible
    ]
    node_details: dict[tuple[str, str], dict[str, object]] = {}
    for run_id, frozen in processing.items():
        summary = frozen.summary
        node_details[("PipelineRun", run_id)] = {
            "label": f"处理运行 {run_id[:12]}",
            "status": summary.status,
            "description": f"处理运行 {run_id}",
            "run_revision": scope.revision,
            "run_id": run_id,
        }
        for step in summary.steps:
            visible = frozenset((*visible, ("NodeRun", step.id)))
            node_details[("NodeRun", step.id)] = {
                "label": f"{step.operator_key} · attempt {step.attempt}",
                "status": step.status,
                "description": (
                    f"{step.operator_key} {step.operator_version}（第 {step.attempt} 次）"
                ),
                "run_id": step.run_id,
                "attempt": step.attempt,
                "operator_key": step.operator_key,
                "operator_version": step.operator_version,
                "config_hash": step.config_hash,
                "sequence": step.sequence,
                "input_refs": [ref.model_dump() for ref in step.input_refs],
                "output_refs": [ref.model_dump() for ref in step.output_refs],
            }
            frozen_rows.append(
                FrozenEdge("PipelineRun", run_id, "NodeRun", step.id, "processed_by")
            )
            for ref in step.input_refs:
                storage_type = {
                    "file": "Asset",
                    "segment": "Segment",
                    "sample": "CandidateSample",
                    "dataset_version": "DatasetVersion",
                }.get(ref.type)
                if storage_type and (storage_type, ref.id) in visible:
                    frozen_rows.append(
                        FrozenEdge(storage_type, ref.id, "NodeRun", step.id, "processed_by")
                    )
            for ref in step.output_refs:
                storage_type = {
                    "file": "Asset",
                    "segment": "Segment",
                    "sample": "CandidateSample",
                    "dataset_version": "DatasetVersion",
                }.get(ref.type)
                if storage_type and (storage_type, ref.id) in visible:
                    frozen_rows.append(
                        FrozenEdge("NodeRun", step.id, storage_type, ref.id, "produced")
                    )
    dataset_rows = session.execute(
        select(DatasetVersion, DatasetDefinition)
        .join(DatasetDefinition, DatasetDefinition.id == DatasetVersion.dataset_id)
        .where(
            DatasetVersion.workspace_id == workspace, DatasetDefinition.workspace_id == workspace
        )
        .limit(max_records + 1)
    )
    dataset_details = {}
    for version, dataset in dataset_rows:
        dataset_details[version.id] = {
            "dataset_id": dataset.id,
            "dataset_version": version.version,
            "dataset_kind": _training_kind(dataset.product_type),
            "label": f"{dataset.name} · {version.version}",
        }
        node_details[("DatasetVersion", version.id)] = dataset_details[version.id]
    sample_rows = session.execute(
        select(CandidateSample, DatasetVersion, DatasetDefinition)
        .join(
            DatasetVersionSample,
            DatasetVersionSample.candidate_sample_id == CandidateSample.id,
        )
        .join(DatasetVersion, DatasetVersion.id == DatasetVersionSample.dataset_version_id)
        .join(DatasetDefinition, DatasetDefinition.id == DatasetVersion.dataset_id)
        .where(
            CandidateSample.workspace_id == workspace,
            DatasetVersion.workspace_id == workspace,
            DatasetDefinition.workspace_id == workspace,
        )
        .order_by(DatasetVersion.created_at, DatasetVersion.id, CandidateSample.id)
        .limit(max_records + 1)
    )
    for sample, version, dataset in sample_rows:
        node_details[("CandidateSample", sample.id)] = {
            "dataset_id": dataset.id,
            "dataset_version": version.version,
            "dataset_kind": _training_kind(dataset.product_type),
            "label": f"{dataset.name} 样本 {sample.id[:12]}",
        }
    return GraphSnapshot(
        scope.revision,
        scope.as_of,
        tuple(
            sorted(
                set(frozen_rows),
                key=lambda row: (row.from_type, row.from_id, row.to_type, row.to_id, row.relation),
            )
        ),
        visible,
        tuple(sorted(node_details.items())),
    )
