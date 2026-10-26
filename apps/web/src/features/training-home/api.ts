import { ApiError, request, type ApiContext } from "../../api/client";
import type { Catalog, Scope } from "../../contracts/training-center";

export function queryString(values: object) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

export async function scopedRequest<T extends { scope: Scope }>(
  path: string, ctx: ApiContext, catalog: Catalog, revision: string | null, signal?: AbortSignal,
): Promise<T> {
  const result = await request<T>(path, ctx, { signal });
  if (!result.scope || result.scope.workspace_id !== ctx.workspaceId || result.scope.catalog !== catalog
    || (revision !== null && result.scope.revision !== revision)) {
    throw new ApiError(409, { error: { code: "SCOPE_MISMATCH", message: "响应范围与当前工作空间、目录或快照不一致，请刷新数据。" } });
  }
  return result;
}
