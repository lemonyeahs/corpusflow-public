import { DEMO_MODE } from "../app/demo-mode";
import { ApiError, BASE_URL, type ApiContext } from "./client";

export interface DownloadResult { blob: Blob; filename: string; contentType: string }
export function downloadFilename(disposition: string | null, fallback: string) {
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition?.match(/filename="([^"]+)"|filename=([^;]+)/i);
  let filename = plain?.[1] || plain?.[2]?.trim() || fallback;
  if (encoded) { try { filename = decodeURIComponent(encoded); } catch { /* Use plain filename. */ } }
  return filename.replace(/[\\/\u0000-\u001f]/g, "_");
}
/** Binary endpoints are deliberately separate from request<T>. No fixture downloads. */
export async function download(path: string, context: ApiContext, fallbackFilename: string, signal?: AbortSignal): Promise<DownloadResult> {
  if (DEMO_MODE) throw new ApiError(409, { error: { code: "FRONTEND_DEMO_ONLY", message: "纯前端演示不连接后端下载，请查看版本清单与样本预览。" } });
  const response = await fetch(`${BASE_URL}${path}`, { signal, headers: { Authorization: `Bearer ${context.token}`, "X-Workspace-ID": context.workspaceId } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: { code: "DOWNLOAD_FAILED", message: "下载失败" } }));
    throw new ApiError(response.status, body);
  }
  return { blob: await response.blob(), filename: downloadFilename(response.headers.get("Content-Disposition"), fallbackFilename), contentType: response.headers.get("Content-Type") || "application/octet-stream" };
}
export function saveDownload({ blob, filename }: DownloadResult) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
