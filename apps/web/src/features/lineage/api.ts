import { request } from "../../api/client";
import type { Catalog, LineageGraph, ObjectType } from "../../contracts/training-center";
import type { ApiContext } from "../../api/client";

export type LineageDirection = "both" | "upstream" | "downstream";

export async function fetchLineageGraph(
  ctx: ApiContext,
  query: {
    catalog: Catalog;
    revision?: string | null;
    rootType: ObjectType;
    rootId: string;
    direction: LineageDirection;
    maxDepth: number;
    maxNodes: number;
  },
  signal?: AbortSignal,
): Promise<LineageGraph> {
  const params = new URLSearchParams({
    catalog: query.catalog,
    root_type: query.rootType,
    root_id: query.rootId,
    direction: query.direction,
    max_depth: String(query.maxDepth),
    max_nodes: String(query.maxNodes),
  });
  if (query.revision) params.set("revision", query.revision);
  return request<LineageGraph>(`/lineage/graph?${params}`, ctx, { signal });
}
