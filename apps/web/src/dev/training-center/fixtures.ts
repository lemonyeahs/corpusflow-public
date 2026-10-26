import type { FileSummary, LineageGraph, OverviewResponse, Paginated, Sample, Scope } from "../../contracts/training-center";

export const fixtureProvenance = {
  schema_version: "1.0.0-draft", revision: "m0-fixture-v1", seed: null,
  generator: "hand-authored: src/dev/training-center/fixtures.ts", generated_at: "2026-10-27T00:00:00Z",
  provenance: "Synthetic development contract examples, not uploaded files or execution history; pending B/C/D review.",
};
export const fixtureScope: Scope = { workspace_id: "fixture-workspace", catalog: "generated", revision: fixtureProvenance.revision, as_of: fixtureProvenance.generated_at, metric_definition_version: "1-draft" };
export const file: FileSummary = {
  id: "fixture-file-1", filename: "接口样例.txt", format: "txt", media_type: "text/plain", size_bytes: 18,
  source_ref: { catalog: "generated", type: "source", id: "fixture-source-1" }, source_kind: "other", ingested_at: null,
  processing_status: "unprocessed", segment_count: null, dataset_refs: [],
};
export const files: Paginated<FileSummary> = { scope: fixtureScope, items: [file], total_count: 1, offset: 0, limit: 20 };
export const overview: OverviewResponse = { scope: fixtureScope, metrics: { files: { value: 1, unit: "文件" }, quality: { value: null, unit: "比例" } }, formats: [], datasets: [], flow: { scope_label: "开发契约样例", stages: [], transitions: [] }, recent_activities: [] };
const common = { id: "fixture-sample-1", dataset_id: "fixture-dataset-1", dataset_version: "v1", split: "train" as const, source_group_id: "fixture-source-1", source_refs: [file.source_ref], segment_refs: [], language: "zh", char_count: 6, token_count: null, token_count_method: null };
export const sampleExamples: Sample[] = [
  { ...common, kind: "cpt", text: "开发契约样例" },
  { ...common, id: "fixture-sample-2", dataset_id: "fixture-dataset-2", char_count: 4, kind: "sft", messages: [{ role: "user", content: "问题" }, { role: "assistant", content: "回答" }] },
  { ...common, id: "fixture-sample-3", dataset_id: "fixture-dataset-3", char_count: 10, kind: "dpo", prompt: "问题", chosen: "首选回答", rejected: "备选回答" },
];
export const graph: LineageGraph = {
  scope: fixtureScope, root: { catalog: "generated", type: "file", id: file.id },
  nodes: [{ id: `generated:file:${file.id}`, ref: { catalog: "generated", type: "file", id: file.id }, kind: "file", label: file.filename, description: "手工编写的契约样例，无处理执行记录", status: null, metrics: {}, detail: {} }],
  edges: [], truncated: false, truncation_reason: null,
};
