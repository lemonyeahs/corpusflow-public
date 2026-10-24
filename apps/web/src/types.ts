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

export interface DocumentVersion {
  document_version_id: string;
  version_no: number;
  content_sha256: string;
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
  error_code?: string | null;
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
}

export interface DatasetVersion {
  dataset_version_id: string;
  version: string;
  status: string;
  sample_count: number;
  content_sha256: string;
  manifest_sha256: string;
  published_at?: string | null;
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
