import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { ErrorState, EmptyState, LoadingState, PageHeader, Panel } from "../../ui";
import { useWorkspaceContext } from "../../app/auth";
import { useCatalogScope } from "../../app/catalog";
import { trainingKeys } from "../../app/query";
import { scopeDestination } from "../../app/scope-navigation";
import type { Catalog, LineageGraph, ObjectType } from "../../contracts/training-center";
import { fetchLineageGraph, type LineageDirection } from "./api";
import styles from "./lineage.module.css";
import "@xyflow/react/dist/style.css";

const TYPES: ObjectType[] = ["source", "file", "operator_run", "segment", "sample", "dataset_version"];
const directions: LineageDirection[] = ["both", "upstream", "downstream"];
const RELATION_LABELS: Record<string, string> = {
  provides: "提供",
  parsed_by: "解析",
  processed_by: "处理",
  produced: "产出",
  derived_from: "派生自",
  included_in: "纳入",
  split_into: "拆分为",
};
const NODE_LINK_LABELS: Record<ObjectType, string> = {
  source: "来源",
  file: "文件",
  operator_run: "处理运行",
  segment: "片段",
  sample: "样本",
  dataset_version: "数据集版本",
};

function nodeLink(node: LineageGraph["nodes"][number], scope: LineageGraph["scope"]) {
  const detail = node.detail;
  const current = new URLSearchParams({ catalog: node.ref.catalog, ...(node.ref.catalog === scope.catalog ? { revision: scope.revision } : {}) });
  const destination = (path: string, extra: Record<string, string>) => `${scopeDestination(path, "/lineage", current)}&${new URLSearchParams(extra)}`;
  if (node.ref.type === "file") return destination("/data/all", { file_id: node.ref.id, detail_tab: "detail" });
  if (node.ref.type === "sample" && typeof detail.dataset_kind === "string" && typeof detail.dataset_id === "string" && typeof detail.dataset_version === "string") {
    return destination(`/datasets/${detail.dataset_kind}`, { dataset_id: detail.dataset_id, version: detail.dataset_version, sample_id: node.ref.id, tab: "samples" });
  }
  if (node.ref.type === "dataset_version" && typeof detail.dataset_kind === "string" && typeof detail.dataset_id === "string" && typeof detail.dataset_version === "string") {
    return destination(`/datasets/${detail.dataset_kind}`, { dataset_id: detail.dataset_id, version: detail.dataset_version });
  }
  if (node.ref.type === "operator_run" && typeof detail.run_id === "string") return destination("/ingest", { run_id: detail.run_id });
  return destination("/lineage", { root_type: node.ref.type, root_id: node.ref.id });
}

function layout(graph: LineageGraph): { nodes: Node[]; edges: Edge[] } {
  const dag = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  dag.setGraph({ rankdir: "LR", nodesep: 42, ranksep: 110 });
  graph.nodes.forEach(node => dag.setNode(node.id, { width: 180, height: 70 }));
  graph.edges.forEach(edge => dag.setEdge(edge.source, edge.target));
  dagre.layout(dag);
  const nodes = graph.nodes.map(node => {
    const position = dag.node(node.id) || { x: 0, y: 0 };
    return {
      id: node.id,
      position: { x: position.x - 90, y: position.y - 35 },
      data: { label: <div className={styles.node} data-kind={node.kind}><strong>{node.label}</strong><small>{node.ref.type} · {node.ref.id}</small></div> },
      draggable: true,
    };
  });
  const edges = graph.edges.map(edge => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: RELATION_LABELS[edge.relation] || "关联",
    animated: false,
  }));
  return { nodes, edges };
}

export default function LineagePage() {
  const ctx = useWorkspaceContext();
  const scope = useCatalogScope();
  const [params, setParams] = useSearchParams();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const catalog = scope.catalog;
  const rootType = (params.get("root_type") || "file") as ObjectType;
  const rootId = params.get("root_id") || "";
  const direction = (directions.includes(params.get("direction") as LineageDirection) ? params.get("direction") : "both") as LineageDirection;
  const maxDepth = Math.min(12, Math.max(1, Number(params.get("max_depth") || 6)));
  const maxNodes = Math.min(500, Math.max(1, Number(params.get("max_nodes") || 200)));
  const query = useQuery({
    queryKey: trainingKeys.query(ctx.workspaceId, catalog, params.get("revision"), "lineage", { rootType, rootId, direction, maxDepth, maxNodes }),
    enabled: rootId.length > 0 && TYPES.includes(rootType),
    queryFn: ({ signal }) => fetchLineageGraph(ctx, { catalog, revision: params.get("revision"), rootType, rootId, direction, maxDepth, maxNodes }, signal),
  });
  useEffect(() => {
    if (!scope.revision && query.data?.scope.catalog === scope.catalog && query.data.scope.workspace_id === ctx.workspaceId) scope.pinScope(query.data.scope);
    // Pin only a successful response for the currently selected workspace and catalog.
  }, [query.data, scope.revision, scope.catalog, ctx.workspaceId]);
  const positioned = useMemo(() => query.data ? layout(query.data) : null, [query.data]);
  const selectedNode = query.data?.nodes.find(node => node.id === selectedNodeId);
  function update(key: string, value: string) { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); setParams(next); }
  return <>
    <PageHeader title="数据血缘" description="按方向和深度追踪真实来源、处理执行与数据集关系。" />
    <Panel title="查询图">
      <div className={styles.toolbar}>
        <label className={styles.field}>目录<select value={catalog} onChange={event => { setSelectedNodeId(null); scope.changeCatalog(event.target.value as Catalog); }}><option value="generated">generated</option><option value="workspace">workspace</option></select></label>
        <label className={styles.field}>根节点 ID<input value={rootId} onChange={event => update("root_id", event.target.value)} placeholder="输入真实对象 ID" /></label>
        <label className={styles.field}>节点类型<select value={rootType} onChange={event => update("root_type", event.target.value)}>{TYPES.map(type => <option key={type}>{type}</option>)}</select></label>
        <label className={styles.field}>方向<select value={direction} onChange={event => update("direction", event.target.value)}>{directions.map(item => <option key={item}>{item}</option>)}</select></label>
        <label className={styles.field}>最大深度<input type="number" min={1} max={12} value={maxDepth} onChange={event => update("max_depth", event.target.value)} /></label>
        <button className="ant-btn ant-btn-primary" onClick={() => void query.refetch()} disabled={!rootId}>查询</button>
      </div>
    </Panel>
    {query.isPending && rootId && <LoadingState label="正在读取血缘图…" />}
    {query.error && <ErrorState error={query.error instanceof ApiError ? new Error(`${query.error.code}：${query.error.message}`) : query.error} onRetry={() => { if (query.error instanceof ApiError && query.error.code === "SNAPSHOT_EXPIRED") void scope.refreshSnapshot(); else void query.refetch(); }} />}
    {!rootId && <EmptyState description="请输入根节点 ID 后查询。" />}
    {query.data && !query.error && <Panel title={`图 · ${query.data.nodes.length} 个节点 / ${query.data.edges.length} 条边`}>
      {query.data.truncated && <div className={styles.notice}>图已截断：达到 {query.data.truncation_reason} 限制。</div>}
      {positioned && <div className={styles.graph}><ReactFlow nodes={positioned.nodes} edges={positioned.edges} fitView nodesConnectable={false} onNodeClick={(_, node) => setSelectedNodeId(node.id)}><Background /><Controls /><MiniMap /></ReactFlow></div>}
      {selectedNode && <div className={styles.detail}>
        <strong>{selectedNode.label}</strong>
        <span>{selectedNode.kind} · {selectedNode.ref.id}</span>
        <p>{selectedNode.description}</p>
        {query.data?.scope && <Link className={styles.detailLink} to={nodeLink(selectedNode, query.data.scope)}>打开{NODE_LINK_LABELS[selectedNode.kind]} ↗</Link>}
        {Object.keys(selectedNode.detail).length > 0 && <pre>{JSON.stringify(selectedNode.detail, null, 2)}</pre>}
      </div>}
    </Panel>}
  </>;
}
