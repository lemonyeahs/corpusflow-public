export type Role = "admin" | "engineer" | "reviewer" | "viewer";

export interface Session {
  token: string;
  user_id: string;
  workspace_id: string;
  role: Role;
}

export interface Workspace {
  workspace_id: string;
  role: Role;
}

export interface Source {
  source_id: string;
  name: string;
  kind: string;
  created_at?: string;
}

export interface Asset {
  asset_id: string;
  filename: string;
  format: string;
  source_id: string;
  quality_status: string;
  ingestion_status?: string;
}

export interface AssetDetail extends Asset {
  source?: Source | null;
  blob?: { storage_key: string; sha256: string; byte_size: number; media_type: string } | null;
  language?: string | null;
  metadata?: Record<string, unknown>;
  document?: { document_id: string; title: string; parse_status: string } | null;
  versions: DocumentVersion[];
}

export interface DashboardOverview {
  as_of: string;
  metric_definition_version: string;
  scope: { workspace_id: string; source_id?: string | null; file_format?: string | null; asset_status?: string | null };
  raw: { source_count: number; asset_count: number; physical_file_count: number; unique_content_count: number; total_bytes: number; authorization: Record<string, number> };
  formats: Record<string, number>;
  business_types: Record<string, number>;
  parsing: { document_count: number; document_version_count: number; segment_count: number; parse_status: Record<string, number>; run_status: Record<string, number>; failure_reasons: Record<string, number> };
  quality: { issue_status: Record<string, number>; issue_count: number; candidate_status: Record<string, number>; candidate_count: number };
  products: Record<string, { versions: number; samples: number; published: number }>;
  recent_versions: Array<{ dataset_version_id: string; dataset_id: string; name: string; product_type: string; version: string; status: string; sample_count: number; published_at?: string | null }>;
  funnel: Array<{ stage: string; count: number; unit: string }>;
}

export interface LineageView {
  asset: { asset_id: string; filename: string; format: string; source_id: string; source_name?: string | null; sha256?: string | null; byte_size?: number | null; media_type?: string | null; metadata?: Record<string, unknown> };
  original: { status: string; url?: string | null; expires_in: number };
  document?: { document_id: string; title: string; parse_status: string } | null;
  selected_version_id?: string | null;
  versions: Array<{
    document_version_id: string;
    version_no: number;
    parser_name: string;
    parser_version: string;
    config_hash: string;
    run_id?: string | null;
    status: string;
    markdown: { status: string; content?: string | null; sha256?: string; artifact_id?: string; content_type?: string };
    structured: { status: string; content?: string | null; data: unknown; sha256?: string; artifact_id?: string; content_type?: string };
    segments: Array<{ segment_id: string; title?: string | null; text: string; location?: Record<string, unknown>; token_count: number; quality_state: string; content_hash: string }>;
  }>;
}

export interface DemoCase {
  case_id: string;
  title: string;
  status: string;
  description: string;
  objects: Record<string, string | null>;
  presence?: Record<string, boolean>;
  metrics?: Record<string, unknown>;
  limitations: string[];
}

export interface DocumentVersion {
  document_version_id: string;
  version_no: number;
  content_sha256: string;
  parser_name?: string;
  parser_version?: string;
  segments?: Segment[];
}

export interface Segment {
  segment_id: string;
  source_id: string;
  document_version_id?: string;
  content_hash: string;
  text: string;
  quality_state?: string;
}

export interface PipelineRun {
  run_id: string;
  asset_id: string;
  status: string;
  snapshot_hash: string;
  revision: number;
  dag?: { nodes?: Array<Record<string, unknown>>; edges?: Array<[string, string]> } | null;
  error_code?: string | null;
  nodes?: NodeRun[];
}

export interface NodeRun {
  node_id: string;
  status: string;
  attempt: number;
  operator_key?: string | null;
  operator_version?: string | null;
  input_count: number;
  output_count: number;
  filtered_count: number;
  duration_ms?: number | null;
  failure_code?: string | null;
  config?: Record<string, unknown>;
  log_ref?: string | null;
}

export interface ProcessingArtifact {
  artifact_id: string;
  kind: string;
  storage_key: string;
  sha256: string;
  immutable: boolean;
}

export interface OperatorDefinition {
  operator_key: string;
  version: string;
  adapter_kind: string;
  params_schema: Record<string, string>;
  available: boolean;
  reason?: string;
}

export interface QualityIssue {
  issue_id: string;
  run_id?: string | null;
  asset_id?: string | null;
  status: string;
  severity: string;
  reason: string;
  rule_version: string;
  created_at: string;
}

export interface QualityMetric {
  metric_id: string; metric_version: string; method: string;
  value: number | null; numerator: number | null; denominator: number | null;
  unit: string; status: string; threshold: number | null; direction: string;
  evidence?: unknown;
}
export interface QualityReportData {
  evaluation_id: string; dataset_version_id: string | null; build_id: string;
  quality_status: string; authorization_gate: string; product_type: string;
  rule_version: string; rule_config_hash: string; sample_count: number;
  metrics: QualityMetric[]; unassessed: string[]; gates: Record<string, boolean>;
  inputs: Array<{ segment_id: string; document_version_id: string; source_id: string }>;
  composition: Record<string, unknown>; processing_records: unknown[];
  generated_at: string;
}
export interface QualityEvaluation {
  evaluation_id: string; status: string; target_type: string; target_id: string;
  report: QualityReportData;
}
export interface QualityRuleConfig { enabled: boolean; threshold: number | null; manual_review: boolean }
export interface QualityRules {
  rule_set: { id: string; name: string };
  versions: Array<{ id: string; version: string; config_hash: string; rules: Record<string, QualityRuleConfig> }>;
}
export interface QualityCoverage {
  asset_count: number; domain_label_occurrences: Record<string, number>;
  domain_unique_assets: Record<string, number>; format_distribution: Record<string, number>;
  year_distribution: Record<string, number>; denominator: string; as_of: string;
  distributions: Record<string, unknown>; authorization: Record<string, unknown>;
}
export interface QualityComparison {
  comparison_id: string;
  comparison: {
    counts: Record<string, number>; quality_comparison: string; quality_reason: string | null;
    token_count_delta: number | null; sample_count_delta: number;
    [key: string]: unknown;
  };
}

export interface Dataset {
  dataset_id: string;
  name: string;
  product_type: string;
  created_at?: string;
}

export interface CandidateSample {
  sample_id: string;
  sample_key: string;
  status: string;
  payload_hash: string;
  payload?: Record<string, unknown>;
  source_id?: string;
}

export interface DatasetVersion {
  dataset_version_id: string;
  version: string;
  status: string;
  sample_count: number;
  content_sha256: string;
  manifest_sha256: string;
  published_at?: string | null;
  product_type?: string;
}

export interface DatasetProductType {
  product_type: string;
  purpose: string;
  schema_version: string;
  description: string;
}

export interface Manifest {
  dataset_id: string;
  dataset_version_id: string;
  build_id: string;
  purpose: string;
  sample_count: number;
  split_counts: Record<string, number>;
  token_count: number;
  tokenizer_version: string;
  content: { storage_key: string; sha256: string; bytes: number };
  authorization?: { purpose: string; status: string };
  quality_snapshot?: { evaluation_id: string; report_sha256: string; rule_version_id: string; quality_status: string };
  quality_report?: { status: string; approved_sample_count: number; review_records: unknown[] };
  input_references?: Array<{ source_id: string; document_version_id: string; segment_id: string }>;
  samples: Array<Record<string, unknown>>;
  published_by: string;
  published_at: string;
}

export interface LineageEdge {
  from_type: string;
  from_id: string;
  to_type: string;
  to_id: string;
  relation: string;
}
