import type {
  Asset, AssetDetail, CandidateSample, Dataset, DatasetProductType, DatasetVersion, LineageEdge, Manifest,
  OperatorDefinition, PipelineRun, ProcessingArtifact, QualityIssue, QualityEvaluation, QualityRules, QualityRuleConfig, QualityReportData, QualityCoverage, QualityComparison, Session, Source, Workspace,
} from "../types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "/api/v1";

export class ApiError extends Error {
  code: string;
  requestId?: string;
  retryable: boolean;
  status: number;
  constructor(status: number, body: { error?: { code?: string; message?: string; retryable?: boolean; request_id?: string } }) {
    const detail = body.error ?? {};
    super(detail.message || `请求失败（${status}）`);
    this.name = "ApiError";
    this.code = detail.code || "HTTP_ERROR";
    this.requestId = detail.request_id;
    this.retryable = Boolean(detail.retryable);
    this.status = status;
  }
}

export interface ApiContext { token: string; workspaceId: string }

export async function request<T>(path: string, context?: ApiContext, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (context?.token) headers.set("Authorization", `Bearer ${context.token}`);
  if (context?.workspaceId) headers.set("X-Workspace-ID", context.workspaceId);
  if (init.body && !(init.body instanceof Blob) && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  const text = await response.text();
  let body: unknown = {};
  try { body = text ? JSON.parse(text) : {}; } catch { body = { error: { code: "INVALID_RESPONSE", message: text } }; }
  if (!response.ok) throw new ApiError(response.status, body as { error?: { code?: string; message?: string; retryable?: boolean; request_id?: string } });
  return body as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  session: (body: { user_id: string; display_name: string; workspace_name: string }) => request<Session>("/auth/session", undefined, json(body)),
  me: (ctx: ApiContext) => request<{ user_id: string; workspaces: Workspace[] }>("/auth/me", ctx),
  workspaces: (ctx: ApiContext) => request<{ items: Workspace[] }>("/workspaces", ctx),
  sources: (ctx: ApiContext) => request<{ items: Source[] }>("/sources", ctx),
  createSource: (ctx: ApiContext, body: { name: string; kind: string }) => request<Source>("/sources", ctx, json(body)),
  stats: (ctx: ApiContext) => request<{ total_assets: number; as_of: string; metric_definition_version: string }>("/assets/stats", ctx),
  assets: (ctx: ApiContext, offset = 0, limit = 20) => request<{ items: Asset[]; total_count: number }>(`/assets?offset=${offset}&limit=${limit}`, ctx),
  asset: (ctx: ApiContext, id: string) => request<AssetDetail>(`/assets/${id}`, ctx),
  initUpload: (ctx: ApiContext, body: { filename: string; size: number; content_type: string }) => request<{ upload_id: string; status: string; object_key: string }>("/uploads/init", ctx, json(body)),
  uploadContent: (ctx: ApiContext, id: string, file: Blob, onProgress?: (value: number) => void) => new Promise<{ upload_id: string; status: string; bytes: number; sha256: string }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `${BASE_URL}/uploads/${id}/content`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("Authorization", `Bearer ${ctx.token}`);
    xhr.setRequestHeader("X-Workspace-ID", ctx.workspaceId);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100)); };
    xhr.onerror = () => reject(new ApiError(0, { error: { code: "NETWORK_ERROR", message: "上传连接失败", retryable: true } }));
    xhr.onload = () => {
      let body: { upload_id: string; status: string; bytes: number; sha256: string } & { error?: { code?: string; message?: string; retryable?: boolean; request_id?: string } } = {} as never;
      try { body = JSON.parse(xhr.responseText) as typeof body; } catch { body = { error: { code: "INVALID_RESPONSE", message: "上传响应无法解析" } } as typeof body; }
      if (xhr.status < 200 || xhr.status >= 300) reject(new ApiError(xhr.status, body));
      else { onProgress?.(100); resolve(body); }
    };
    xhr.send(file);
  }),
  completeUpload: (ctx: ApiContext, id: string, checksum: string) => request<{ upload_id: string; status: string; sha256: string }>(`/uploads/${id}/complete`, ctx, json({ checksum })),
  ingest: (ctx: ApiContext, body: { upload_ids: string[]; source_id: string }) => request<{ batch_id: string; status: string; totals: Record<string, number>; items: Array<{ upload_id: string; asset_id?: string; status: string; error_code?: string }> }>("/ingest-batches", ctx, json(body)),
  createRuns: (ctx: ApiContext, body: { asset_ids: string[]; config: Record<string, unknown> }) => request<{ batch_id: string; status: string; accepted: Array<{ run_id: string; asset_id: string }>; rejected: Array<{ asset_id: string; reason: string }> }>("/pipeline-runs/batches", ctx, json(body)),
  run: (ctx: ApiContext, id: string) => request<PipelineRun>(`/pipeline-runs/${id}`, ctx),
  runArtifacts: (ctx: ApiContext, id: string) => request<{ items: ProcessingArtifact[] }>(`/pipeline-runs/${id}/artifacts`, ctx),
  operators: (ctx: ApiContext) => request<{ items: OperatorDefinition[] }>("/processing/operators", ctx),
  runLogs: (ctx: ApiContext, id: string) => request<{ items: Array<{ level: string; message: string; attempt: number; created_at: string }> }>(`/pipeline-runs/${id}/logs`, ctx),
  resumeRun: (ctx: ApiContext, id: string) => request<{ run_id: string; status: string; queued: boolean }>(`/pipeline-runs/${id}/resume`, ctx, json({})),
  issues: (ctx: ApiContext, status?: string) => request<{ items: QualityIssue[] }>(`/quality/issues${status ? `?status=${encodeURIComponent(status)}` : ""}`, ctx),
  reviewIssue: (ctx: ApiContext, id: string, body: { decision: string; note: string }) => request<{ issue_id: string; status: string }>(`/quality/issues/${id}/reviews`, ctx, json(body)),
  qualityRules: (ctx: ApiContext) => request<QualityRules>("/quality/rules", ctx),
  createQualityRuleVersion: (ctx: ApiContext, body: { version: string; rules: Record<string, QualityRuleConfig> }) => request<{ id: string; version: string }>("/quality/rules/versions", ctx, json(body)),
  evaluateQuality: (ctx: ApiContext, body: { target_type: "dataset_build" | "dataset_version"; target_id: string; rule_version_id?: string; idempotency_key?: string }) => request<QualityEvaluation>("/quality/evaluations", ctx, json(body)),
  qualityEvaluations: (ctx: ApiContext) => request<{ items: Array<{ evaluation_id: string; target_type: string; target_id: string; status: string; quality_status: string; created_at: string }> }>("/quality/evaluations", ctx),
  qualityEvaluation: (ctx: ApiContext, id: string) => request<QualityEvaluation>(`/quality/evaluations/${id}`, ctx),
  qualityReport: (ctx: ApiContext, versionId: string) => request<{ report_id: string; dataset_version_id: string; sha256: string; report: QualityReportData }>(`/quality/reports/${versionId}`, ctx),
  qualityCoverage: (ctx: ApiContext, params = "") => request<QualityCoverage>(`/quality/coverage${params ? `?${params}` : ""}`, ctx),
  qualityRatios: (ctx: ApiContext, versionId: string) => request<Record<string, unknown>>(`/quality/ratios/${versionId}`, ctx),
  compareQualityVersions: (ctx: ApiContext, body: { left_version_id: string; right_version_id: string }) => request<QualityComparison>("/quality/version-comparisons", ctx, json(body)),
  datasets: (ctx: ApiContext) => request<{ items: Dataset[] }>("/datasets", ctx),
  datasetProductTypes: (ctx: ApiContext) => request<{ items: DatasetProductType[] }>("/dataset-products/types", ctx),
  createDataset: (ctx: ApiContext, body: { name: string; product_type: string }) => request<Dataset>("/datasets", ctx, json(body)),
  preview: (ctx: ApiContext, body: { product_type: string; purpose: string; segment_ids: string[] }) => request<{ included: Array<{ segment_id: string; reason: string }>; excluded: Array<{ segment_id: string; reason: string }>; included_count: number; excluded_count: number }>("/dataset-builds/preview", ctx, json(body)),
  createBuild: (ctx: ApiContext, body: { dataset_id: string; segment_ids: string[]; purpose: string; config: Record<string, unknown> }) => request<{ build_id: string; config_hash: string; status: string; candidate_count: number; product_type: string; excluded: Array<Record<string, string>>; metrics: Record<string, unknown> }>("/dataset-builds", ctx, json(body)),
  candidates: (ctx: ApiContext, buildId: string) => request<{ items: CandidateSample[] }>(`/dataset-builds/${buildId}/candidates`, ctx),
  buildQualityReport: (ctx: ApiContext, buildId: string) => request<{ build_id: string; product_type: string; status: string; config_hash: string; metrics: Record<string, unknown>; excluded: Array<Record<string, string>>; candidate_count: number; approved_count: number; rejected_count: number }>(`/dataset-builds/${buildId}/quality-report`, ctx),
  reviewSample: (ctx: ApiContext, id: string, body: { decision: "approved" | "rejected"; note: string }) => request<{ sample_id: string; status: string }>(`/candidate-samples/${id}/reviews`, ctx, json(body)),
  validateBuild: (ctx: ApiContext, id: string) => request<{ build_id: string; ok: boolean; checks: Array<{ sample_id: string; ok: boolean; reason: string }>; release_candidate_hash: string }>(`/dataset-builds/${id}/validate`, ctx, json({})),
  versions: (ctx: ApiContext, datasetId: string) => request<{ items: DatasetVersion[] }>(`/datasets/${datasetId}/versions`, ctx),
  publish: (ctx: ApiContext, datasetId: string, body: { build_id: string; version: string }) => request<{ dataset_version_id: string; status: string; manifest_sha256: string; content_sha256: string; sample_count: number; content_storage_key: string }>(`/datasets/${datasetId}/versions`, ctx, { ...json(body), headers: { "Idempotency-Key": `${body.build_id}:${body.version}` } }),
  manifest: (ctx: ApiContext, datasetId: string, version: string) => request<Manifest>(`/datasets/${datasetId}/versions/${encodeURIComponent(version)}/manifest`, ctx),
  download: (ctx: ApiContext, datasetId: string, version: string, purpose: string) => request<{ dataset_version_id: string; version: string; url: string; expires_in: number; purpose: string }>(`/datasets/${datasetId}/versions/${encodeURIComponent(version)}/download?purpose=${encodeURIComponent(purpose)}`, ctx),
  lineage: (ctx: ApiContext, type: string, id: string) => request<{ object_type: string; object_id: string; edges: LineageEdge[]; as_of: string }>(`/lineage/${encodeURIComponent(type)}/${encodeURIComponent(id)}`, ctx),
  members: (ctx: ApiContext, workspaceId: string, body: { user_id: string; role: string }) => request<{ workspace_id: string; user_id: string; role: string }>(`/workspaces/${workspaceId}/members`, ctx, json(body)),
  audit: (ctx: ApiContext) => request<{ items: Array<{ event_id: string; action: string; resource_type: string; resource_id: string; actor_id: string; summary: Record<string, unknown> }> }>("/audit-events", ctx),
};
