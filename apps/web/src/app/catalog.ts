import { useSearchParams } from "react-router-dom";
import type { Catalog, Scope } from "../contracts/training-center";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkspaceContext } from "./auth";
import { trainingKeys } from "./query";

/** Pin the first server revision in the URL before requesting dependent resources. */
export function useCatalogScope() {
  const [params, setParams] = useSearchParams();
  const { workspaceId } = useWorkspaceContext();
  const client = useQueryClient();
  const catalog: Catalog = params.get("catalog") === "workspace" ? "workspace" : "generated";
  const revision = params.get("revision");
  function pinScope(scope: Scope) {
    if (scope.catalog !== catalog || scope.workspace_id !== workspaceId) throw new Error("响应范围与当前工作空间或目录不一致");
    if (revision && revision !== scope.revision) throw new Error("响应快照与当前版本不一致");
    if (revision === scope.revision && params.get("catalog") === catalog) return;
    setParams(previous => { const next = new URLSearchParams(previous); next.set("catalog", catalog); next.set("revision", scope.revision); return next; }, { replace: true });
  }
  function changeCatalog(nextCatalog: Catalog) {
    setParams(previous => { const next = new URLSearchParams(previous); next.set("catalog", nextCatalog); ["revision", "offset", "dataset_id", "version", "sample_id"].forEach(key => next.delete(key)); return next; });
  }
  async function refreshSnapshot() {
    // Also remove the unpinned bootstrap query so an expired revision cannot be re-pinned.
    const queryKey = trainingKeys.catalog(workspaceId, catalog);
    await client.cancelQueries({ queryKey });
    client.removeQueries({ queryKey });
    setParams(previous => { const next = new URLSearchParams(previous); next.delete("revision"); next.delete("offset"); return next; }, { replace: true });
  }
  return { catalog, revision, pinScope, changeCatalog, refreshSnapshot };
}
