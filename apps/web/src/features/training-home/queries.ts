import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useWorkspaceContext } from "../../app/auth";
import { useCatalogScope } from "../../app/catalog";
import { trainingKeys } from "../../app/query";
import type { OverviewResponse, Scope } from "../../contracts/training-center";
import { queryString, scopedRequest } from "./api";

/** Only the entry query may bootstrap a revision; all dependent queries wait for it. */
export function useCatalogQuery<T extends { scope: Scope }>(resource: string, path: string, filters: object = {}, enabled = true, bootstrap = false) {
  const ctx = useWorkspaceContext();
  const scope = useCatalogScope();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, resource, { path, ...filters }),
    queryFn: ({ signal }) => scopedRequest<T>(`${path}?${queryString({ ...filters, catalog: scope.catalog, revision: scope.revision })}`, ctx, scope.catalog, scope.revision, signal),
    enabled: enabled && (bootstrap || !!scope.revision),
  });
  useEffect(() => {
    if (!bootstrap || scope.revision || !query.data) return;
    // Seed the pinned key to avoid a second request with an already validated response.
    client.setQueryData(trainingKeys.query(ctx.workspaceId, scope.catalog, query.data.scope.revision, resource, { path, ...filters }), query.data);
    scope.pinScope(query.data.scope);
  }, [query.data, scope.revision, scope.catalog, ctx.workspaceId, resource, client]);
  return query;
}

export function useOverview() {
  return useCatalogQuery<OverviewResponse>("overview", "/training-center/overview", {}, true, true);
}
