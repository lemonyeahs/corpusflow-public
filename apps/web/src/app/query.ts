import { QueryClient } from "@tanstack/react-query";
import type { Catalog } from "../contracts/training-center";

export function createQueryClient() {
  return new QueryClient({ defaultOptions: {
    queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  } });
}
export const trainingKeys = {
  workspace: (workspaceId: string) => ["training-center", workspaceId] as const,
  catalog: (workspaceId: string, catalog: Catalog) => [...trainingKeys.workspace(workspaceId), catalog] as const,
  scope: (workspaceId: string, catalog: Catalog, revision: string | null) =>
    [...trainingKeys.catalog(workspaceId, catalog), revision] as const,
  query: (workspaceId: string, catalog: Catalog, revision: string | null, resource: string, filters: object = {}) =>
    [...trainingKeys.scope(workspaceId, catalog, revision), resource, filters] as const,
};
