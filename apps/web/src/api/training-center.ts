import type { QueryClient } from "@tanstack/react-query";
import { ApiError, request, type ApiContext } from "./client";
import { trainingKeys } from "../app/query";
import type { Catalog, Scope } from "../contracts/training-center";

export function queryString(values: object) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

function mismatch() {
  return new ApiError(409, { error: { code: "SCOPE_MISMATCH", message: "响应范围与当前工作空间、目录或快照不一致，请刷新数据。" } });
}

/** Metadata belongs to a snapshot, never to one resource or filter. */
export function acceptScope(client: QueryClient, scope: Scope) {
  const prefix = [...trainingKeys.catalog(scope.workspace_id, scope.catalog), "scope-metadata"];
  const key = [...prefix, scope.revision];
  const previous = client.getQueryData<Scope>(key);
  if (previous && (previous.as_of !== scope.as_of || previous.metric_definition_version !== scope.metric_definition_version)) throw mismatch();
  // Keep the invariant for the lifetime of cached data; scope refresh/logout removes it explicitly.
  client.setQueryDefaults(prefix, { gcTime: Infinity });
  client.setQueryData(key, scope);
}

export async function scopedRequest<T extends { scope: Scope }>(
  path: string, ctx: ApiContext, catalog: Catalog, revision: string | null, signal?: AbortSignal,
  options: { expectedScope?: Scope; client?: QueryClient } = {},
): Promise<T> {
  const result = await request<T>(path, ctx, { signal });
  signal?.throwIfAborted();
  const scope = result?.scope;
  if (!scope || scope.workspace_id !== ctx.workspaceId || scope.catalog !== catalog
    || typeof scope.revision !== "string" || !scope.revision.trim()
    || (revision !== null && scope.revision !== revision)
    || typeof scope.as_of !== "string" || !/(Z|\+00:00)$/.test(scope.as_of) || !Number.isFinite(Date.parse(scope.as_of))
    || typeof scope.metric_definition_version !== "string" || !scope.metric_definition_version.trim()) throw mismatch();
  const expected = options.expectedScope;
  if (expected && (scope.workspace_id !== expected.workspace_id || scope.catalog !== expected.catalog
    || scope.revision !== expected.revision || scope.as_of !== expected.as_of
    || scope.metric_definition_version !== expected.metric_definition_version)) throw mismatch();
  if (options.client) acceptScope(options.client, scope);
  return result;
}
