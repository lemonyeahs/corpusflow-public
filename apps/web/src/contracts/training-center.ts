/** M0 draft v1: manually maintained frontend DTOs, pending B/C/D review.
 * No new backend endpoint is implied by these types. Unknown evidence stays null.
 */
export const CONTRACT_VERSION = "1.0.0-draft";
export const FORMATS = ["all", "pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl", "other"] as const;
export const TRAINING_KINDS = ["cpt", "sft", "dpo"] as const;
export type DataFormat = typeof FORMATS[number];
export type TrainingKind = typeof TRAINING_KINDS[number];
export type Catalog = "generated" | "workspace";
export type Split = "train" | "validation" | "test";
export type ExportFormat = "jsonl" | "markdown" | "csv" | "txt";
export type SourceKind = "web" | "book" | "paper" | "other";
export type ObjectType = "source" | "file" | "operator_run" | "segment" | "sample" | "dataset_version";
export interface ObjectRef { catalog: Catalog; type: ObjectType; id: string }
export interface Scope { workspace_id: string; catalog: Catalog; revision: string; as_of: string; metric_definition_version: string }
export interface ApiErrorBody { error: { code: string; message: string; retryable?: boolean; request_id?: string; details?: Record<string, unknown> } }
export interface Paginated<T> { scope: Scope; items: T[]; total_count: number; offset: number; limit: number }
export interface CatalogParams { catalog: Catalog; revision?: string }
export interface PaginationParams { offset?: number; limit?: number }
export interface FileFilters extends CatalogParams, PaginationParams { format?: DataFormat; q?: string; source_kind?: SourceKind; language?: string; status?: ProcessingStatus }
export interface SampleFilters extends CatalogParams, PaginationParams { version: string; split?: Split; q?: string }
export type ProcessingStatus = "unprocessed" | "queued" | "running" | "succeeded" | "partial" | "failed";
export interface Metric {
  value: number | null; unit: string; numerator?: number; denominator?: number;
  delta?: number | null; comparison_period?: { from: string; to: string };
}
export interface Distribution { measure: string; unit: string; total_count: number; buckets: Array<{ key: string; label: string; count: number; ratio: number | null }> }
export interface TimeSeries { timezone: string; from: string; to: string; unit: string; points: Array<{ date: string; count: number }> }
export interface Flow {
  scope_label: string;
  stages: Array<{ key: string; label: string; count: number | null; unit: string }>;
  transitions: Array<{ from: string; to: string; relation: string; retention_ratio: number | null }>;
}
export interface SampleBase {
  id: string; dataset_id: string; dataset_version: string; split: Split; source_group_id: string;
  source_refs: ObjectRef[]; segment_refs: ObjectRef[]; language: string | null;
  char_count: number; token_count: number | null; token_count_method: string | null;
}
export interface CptSample extends SampleBase { kind: "cpt"; text: string; title?: string }
export interface SftSample extends SampleBase { kind: "sft"; messages: Array<{ role: "system" | "user" | "assistant"; content: string }> }
export interface DpoSample extends SampleBase { kind: "dpo"; prompt: string; chosen: string; rejected: string; preference_reason?: string }
export type Sample = CptSample | SftSample | DpoSample;
export interface FileSummary {
  id: string; filename: string; format: Exclude<DataFormat, "all">; media_type: string; size_bytes: number;
  source_ref: ObjectRef; source_kind: SourceKind; ingested_at: string | null;
  processing_status: ProcessingStatus; segment_count: number | null; dataset_refs: ObjectRef[];
}
export interface DatasetSummary {
  id: string; version: string; kind: TrainingKind; name: string; record_count: number;
  record_unit: string; split_counts: Record<Split, number>; token_count: number | null;
  token_count_method: string | null; status: string; source_refs: ObjectRef[];
}
// Nested overview/activity/manifest payload fields need Agent 2 review. Keep them unknown
// instead of inventing an executable backend contract or casting them to any.
export interface OverviewResponse {
  scope: Scope; metrics: Record<string, Metric>; formats: unknown[]; datasets: DatasetSummary[];
  flow: Flow; recent_activities: unknown[];
}
export interface FormatStatsResponse {
  scope: Scope; metrics: Record<string, Metric>; flow: Flow; ingestion_trend: TimeSeries;
  length_distribution: Distribution; language_distribution: Distribution; source_distribution: Distribution; dataset_refs: ObjectRef[];
}
export interface DatasetsResponse { scope: Scope; items: DatasetSummary[] }
export interface DatasetOverviewResponse {
  scope: Scope; dataset: DatasetSummary; split_counts: Record<Split, number>;
  source_distribution: Distribution; destination_counts: Record<string, number>;
  length_distribution: Distribution; language_distribution: Distribution; lineage_root_ref: ObjectRef;
}
export interface ProcessingStepSummary {
  id: string; run_id: string; attempt: number; operator_key: string; operator_version: string; config_hash: string;
  sequence: number; status: Exclude<ProcessingStatus, "unprocessed">;
  input_count: number | null; output_count: number | null;
  input_unit: "file" | "record" | "segment"; output_unit: "file" | "record" | "segment";
  modified_count: number | null; filtered_count: number | null; failed_count: number | null;
  input_refs: ObjectRef[]; output_refs: ObjectRef[]; started_at: string | null; completed_at: string | null;
}
export interface LineageGraph {
  scope: Scope; root: ObjectRef;
  nodes: Array<{ id: string; ref: ObjectRef; kind: ObjectType; label: string; description: string;
    status: string | null; metrics: Record<string, number | null>; detail: Record<string, unknown> }>;
  edges: Array<{ id: string; source: string; target: string; relation: string }>;
  truncated: boolean; truncation_reason: "max_depth" | "max_nodes" | null;
}
export const PRODUCT_TYPE: Record<TrainingKind, "pretrain" | "sft" | "dpo"> = { cpt: "pretrain", sft: "sft", dpo: "dpo" };
