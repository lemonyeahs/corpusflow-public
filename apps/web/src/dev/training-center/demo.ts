/** Authored synthetic presentation data; no HTTP, database or Worker execution.
 * 300,000 logical records are generated on demand, never allocated as a giant array.
 */
import type { Catalog, DatasetSummary, FileSummary, Sample, Scope, Unit } from "../../contracts/training-center";
import { cases, datasetOverview } from "./fixtures";
import { demoSession } from "../../app/demo-mode";
const timestamp = "2026-10-27T08:30:00Z";
const topics = ["城市绿色能源发展报告", "大语言模型技术白皮书", "智慧农业实践指南", "数字文化与知识传播", "智能制造质量管理", "海洋生态保护研究", "企业知识库建设手册", "开放科学与数据治理", "自然语言处理入门", "可持续交通规划"];
const paragraphs = [
  "城市能源系统正在从单一供给转向多源协同。分布式光伏、储能设施与柔性负荷共同参与调度，使能源供需能够在更小的时间尺度内保持平衡。建设过程中，应结合本地气候、用能结构和公共设施布局，分阶段评估实际效益。",
  "高质量语料建设需要同时关注内容覆盖、结构完整与来源可追溯。文档完成解析后，应保留章节层级和表格上下文，再进行字符规范、重复检测与敏感信息处理。训练集与评估集按来源分组划分，避免相似内容跨集合造成评价偏差。",
  "知识服务的价值不仅来自信息数量，也来自组织方式。把分散的研究材料转化为主题明确、引用完整的知识单元，可以帮助使用者快速发现关联。对于存在争议的结论，应保留适用条件与证据范围，并为后续更新提供清晰入口。",
];
const questions = ["如何为企业知识库设计高质量的数据清洗流程？", "请概括绿色能源系统建设的三个关键环节。", "如何避免训练集与评估集之间出现数据泄漏？", "一份技术报告应如何组织成可检索的知识单元？", "设计数据质量评估方案时应该关注哪些指标？", "怎样保留文档清洗前后的可追溯关系？"];
const answers = ["建议分为四步：首先核对文档来源与使用范围；其次保留章节结构，规范编码与空白字符；然后执行重复检测与敏感字段脱敏；最后抽样复核，并记录处理规则和版本。每个步骤均保留输入、输出及异常记录，便于回溯。", "三个关键环节是需求分析、协同规划和效果评估。先分析气候条件与用能结构，再统筹发电、储能和负荷调度，最后用实际运行数据评估能效与稳定性，逐步优化。", "按来源或文档组划分数据，先划分再构建样本；对跨集合内容进行近重复检测；保留分组规则、切分种子与版本信息。发现泄漏时重新评估，不能仅删除几个相同句子。"];
answers.push(
  "先按主题和章节划分文档，保留标题、出处、时间与适用条件。每个知识单元围绕一个完整问题组织正文，关联必要的表格或引用，并记录稳定的文档标识和版本，方便检索与更新。",
  "建议覆盖完整性、准确性、一致性、重复率、可读性与来源合规六个维度。为每个指标定义计算口径和抽样方法，保留基线与异常清单，避免只用单一分数代替具体问题分析。",
  "为原始记录分配稳定标识，在每个处理步骤保存输入引用、输出引用、规则版本和变更原因。清洗后的片段继续关联原文位置，通过同一记录标识查看处理前后内容，并保留人工复核入口。",
);
const formats = ["pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl"] as const;
const formatCounts = [240, 180, 150, 210, 120, 90, 120, 90];
const sourceKinds = ["paper", "web", "book", "other"] as const;
const counts = { cpt: 140000, sft: 105000, dpo: 55000 };
const names = { cpt: "通识与行业知识语料", sft: "专业问答与多轮对话", dpo: "回答质量与偏好对齐" };
type Kind = keyof typeof counts;
const kinds = Object.keys(counts) as Kind[];
const metric = (value: number, unit: Unit) => ({ value, unit });
function distribution(values: Record<string, number>, unit: Unit, measure: string) {
  const total = Object.values(values).reduce((a, b) => a + b, 0);
  return { measure, unit, total_count: total, buckets: Object.entries(values).map(([key, count]) => ({ key, label: key, count, ratio: total ? count / total : null })) };
}
function data(catalog: Catalog) {
  const ref = (type: "source" | "dataset_version", id: string) => ({ catalog, type, id });
  const datasets: DatasetSummary[] = kinds.map(kind => ({ id: `demo-${kind}`, workspace_id: demoSession.workspace_id, version: "2026.10", version_id: `demo-${kind}-v1`, kind, product_type: kind === "cpt" ? "pretrain" : kind, name: names[kind], record_count: counts[kind], record_unit: kind === "cpt" ? "article" : kind === "sft" ? "record" : "pair", split_counts: { train: counts[kind] * .9, validation: counts[kind] * .05, test: counts[kind] * .05 }, token_count: counts[kind] * 384, token_count_method: "synthetic-demo-budget", status: "available", source_refs: Array.from({ length: 10 }, (_, i) => ref("source", `demo-source-${i}`)) }));
  let sequence = 0;
  const files: FileSummary[] = formats.flatMap((format, f) => Array.from({ length: formatCounts[f] }, (_, n) => {
    const i = sequence++;
    return { id: `demo-file-${i}`, workspace_id: demoSession.workspace_id, filename: `${topics[i % topics.length]}_${String(n + 1).padStart(3, "0")}.${format}`, format, media_type: "text/plain", size_bytes: 58000 + (i * 7919) % 9000000, source_ref: ref("source", `demo-source-${i % 10}`), source_kind: sourceKinds[(i % 10) % 4], language: i % 5 ? "zh" : "en", ingested_at: `2026-10-${String(1 + (i * 7 + Math.floor(i / 27)) % 27).padStart(2, "0")}T08:00:00Z`, processing_status: "succeeded" as const, segment_count: 200 + i % 101, dataset_refs: datasets.map(d => ref("dataset_version", d.version_id)) };
  }));
  return { datasets, files };
}
const catalogs = { generated: data("generated"), workspace: data("workspace") };
function sample(d: DatasetSummary, n: number, catalog: Catalog): Sample {
  const i = n - 1, text = paragraphs[i % 3];
  const common = { id: `${d.id}-sample-${n}`, workspace_id: demoSession.workspace_id, kind: d.kind, dataset_id: d.id, dataset_version: d.version, sequence: n, split: (n <= d.split_counts.train ? "train" : n <= d.split_counts.train + d.split_counts.validation ? "validation" : "test") as "train" | "validation" | "test", source_group_id: `demo-group-${d.kind}-${Math.floor(i / 50)}`, source_refs: [{ catalog, type: "source" as const, id: `demo-source-${i % 10}` }], segment_refs: [], language: "zh", token_count: null, token_count_method: null };
  if (d.kind === "cpt") return { ...common, kind: "cpt", title: `${topics[i % 10]} · 第 ${n} 节`, text: `${text}\n\n${paragraphs[(i + 1) % 3]}`, char_count: [...text + "\n\n" + paragraphs[(i + 1) % 3]].length };
  if (d.kind === "sft") {
    const messages = [{ role: "system" as const, content: "请给出清晰、可靠且有操作步骤的回答。" }, { role: "user" as const, content: questions[i % 6] }, { role: "assistant" as const, content: answers[i % answers.length] }, { role: "user" as const, content: "实际落地时，如何检查效果？" }, { role: "assistant" as const, content: "选取具有代表性的样本建立基线，对比处理前后的完整性、重复率和可读性。记录异常类型，定期复核，按结果调整规则。" }];
    return { ...common, kind: "sft", messages, char_count: messages.reduce((sum, m) => sum + [...m.content].length, 0) };
  }
  const prompt = questions[i % 6], chosen = answers[i % answers.length], rejected = "直接使用现有数据即可，不需要检查来源、内容完整性或划分方式。";
  return { ...common, kind: "dpo", prompt, chosen, rejected, preference_reason: "优选回答提供明确步骤、适用条件和检查方法；非优选回答忽略必要的数据质量检查。", char_count: [...prompt + chosen + rejected].length };
}
function sampleLengths(d: DatasetSummary, catalog: Catalog) {
  const buckets = { "0-127": 0, "128-255": 0, "256+": 0 };
  // Content repeats every 30 records (LCM of topic/question/paragraph variants).
  for (let n = 1; n <= 30; n++) {
    const length = sample(d, n, catalog).char_count;
    buckets[length < 128 ? "0-127" : length < 256 ? "128-255" : "256+"] += Math.floor((d.record_count - n) / 30) + 1;
  }
  return distribution(buckets, d.record_unit, "training_record_char_length");
}
export function demoResponse(path: string, init: RequestInit = {}): Response {
  const url = new URL(path, "http://frontend-demo.invalid"), q = url.searchParams;
  const catalog: Catalog = q.get("catalog") === "workspace" ? "workspace" : "generated";
  const scope: Scope = { catalog, workspace_id: demoSession.workspace_id, revision: q.get("revision") || "frontend-demo-300k-v1", as_of: timestamp, metric_definition_version: "1.0.0" };
  const { files, datasets } = catalogs[catalog];
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "X-CorpusFlow-Mode": "frontend-demo" } });
  const fail = (message = "纯前端演示不执行后端写入或下载操作", status = 409) => json({ error: { code: "FRONTEND_DEMO_ONLY", message } }, status);
  if ((init.method || "GET") !== "GET") return fail();
  if (url.pathname === "/auth/me") return json({ user_id: demoSession.user_id });
  if (url.pathname === "/workspaces") return json({ items: [{ workspace_id: demoSession.workspace_id, role: "admin" }] });
  const offset = Math.max(0, Number(q.get("offset") || 0)), limit = Math.min(100, Math.max(1, Number(q.get("limit") || 20)));
  const page = (items: unknown[], total = items.length) => ({ scope, items: items.slice(offset, offset + limit), total_count: total, offset, limit });
  const format = url.pathname.match(/\/formats\/([^/]+)\/stats/)?.[1] || q.get("format");
  const selected = files.filter(f => (!format || format === "all" || f.format === format) && (!q.get("source_kind") || f.source_kind === q.get("source_kind")) && (!q.get("language") || f.language === q.get("language")) && (!q.get("status") || f.processing_status === q.get("status")));
  const segments = selected.reduce((sum, f) => sum + (f.segment_count || 0), 0);
  const flow = { scope_label: "当前范围 · 文件、片段与训练记录", stages: [{ key: "files", label: "原始文件", count: selected.length, unit: "file" }, { key: "segments", label: "结构化片段", count: segments, unit: "segment" }, ...datasets.map(d => ({ key: d.kind, label: d.kind.toUpperCase(), count: Math.round(d.record_count * selected.length / files.length), unit: d.record_unit }))], transitions: [{ from: "files", to: "segments", relation: "parsed_by", retention_ratio: null }, { from: "segments", to: "cpt", relation: "included_in", retention_ratio: null }, { from: "segments", to: "sft", relation: "included_in", retention_ratio: null }, { from: "segments", to: "dpo", relation: "included_in", retention_ratio: null }] };
  if (url.pathname === "/training-center/overview") return json({ scope, metrics: { file_count: metric(files.length, "file"), segment_count: metric(segments, "segment"), training_record_count: metric(300000, "record"), token_count: metric(115200000, "token"), quality_pass_rate: { ...metric(.968, "ratio"), numerator: 290400, denominator: 300000 } }, formats: [...formats, "other"].map(f => ({ format: f, file_count: files.filter(file => file.format === f).length, unit: "file" })), datasets, flow, recent_activities: ["行业知识语料 v2026.10 已就绪", "多轮对话数据完成质量检查", "偏好数据集完成版本切分", "技术文档完成字符规范与脱敏"].map((label, i) => ({ id: `activity-${i}`, label, occurred_at: `2026-10-27T0${8 - i}:20:00Z`, ref: { catalog, type: "dataset_version", id: datasets[i % 3].version_id } })) });
  if (url.pathname.endsWith("/stats")) {
    const buckets = (field: "source_kind" | "language", weighted = false) => selected.reduce<Record<string, number>>((acc, f) => { acc[f[field] || "unknown"] = (acc[f[field] || "unknown"] || 0) + (weighted ? f.segment_count || 0 : 1); return acc; }, {});
    const short = Math.floor(segments * .18), medium = Math.floor(segments * .47);
    return json({ scope, metrics: { file_count: metric(selected.length, "file"), segment_count: metric(segments, "segment"), size_bytes: metric(selected.reduce((s, f) => s + f.size_bytes, 0), "byte"), token_count: metric(segments * 384, "token"), quality_pass_rate: metric(.968, "ratio") }, flow, availability: { ingestion_trend: selected.length ? "available" : "no_files" }, ingestion_trend: { timezone: "UTC", from: "2026-10-01", to: "2026-10-27", unit: "file", points: Array.from({ length: 27 }, (_, i) => { const date = `2026-10-${String(i + 1).padStart(2, "0")}`; return { date, count: selected.filter(f => f.ingested_at?.startsWith(date)).length }; }) }, length_distribution: distribution({ "0-127": short, "128-255": medium, "256+": segments - short - medium }, "segment", "segment_char_length"), language_distribution: distribution(buckets("language", true), "segment", "segment_language"), source_distribution: distribution(buckets("source_kind"), "file", "file_source_kind"), dataset_refs: selected.length ? datasets.map(d => ({ catalog, type: "dataset_version", id: d.version_id })) : [] });
  }
  if (url.pathname === "/training-center/files") return json(page(selected.filter(f => f.filename.toLowerCase().includes((q.get("q") || "").toLowerCase())).sort((a, b) => a.filename.localeCompare(b.filename))));
  const fileMatch = url.pathname.match(/^\/training-center\/files\/([^/]+)(\/comparison)?$/);
  if (fileMatch) {
    const file = files.find(f => f.id === fileMatch[1]);
    if (!file) return fail("未找到演示文件", 404);
    if (!fileMatch[2]) return json({ scope, file, source: { id: file.source_ref.id, name: "玄知知识工程 · 内容研究组", kind: file.source_kind, author: "资料编辑团队", url: null, license: "仅用于界面演示" }, processing_summary_ref: { catalog: "workspace", type: "pipeline_run", id: `run-${file.id}` }, dataset_refs: file.dataset_refs });
    return json({ scope, before: { record_id: `record-${file.id}`, text: "企业知识库建设指南\n\n　数据  质量是知识服务的基础。ＡＩ 系统需要统一文本编码，去除重复空白。\n联系人：demo.editor@example.invalid\n\n来源标识和版本信息应当完整保留。" }, after: { record_id: `record-${file.id}`, text: "企业知识库建设指南\n\n数据质量是知识服务的基础。AI 系统需要统一文本编码，去除重复空白。\n联系人：[EMAIL]\n\n来源标识和版本信息应当完整保留。" }, changes: ["统一全角字符与文本编码", "合并重复空白，保留段落结构", "识别邮箱字段并替换为脱敏占位符"], applied_steps: [{ catalog, type: "operator_run", id: "demo-normalize" }, { catalog, type: "operator_run", id: "demo-redact" }], record_ref: { catalog, type: "segment", id: `record-${file.id}` }, processing_run_ref: { catalog: "workspace", type: "pipeline_run", id: `run-${file.id}` } });
  }
  if (url.pathname === "/training-center/datasets") return json({ scope, items: datasets.filter(d => !q.get("kind") || d.kind === q.get("kind")) });
  const match = url.pathname.match(/^\/training-center\/datasets\/([^/]+)\/(overview|samples|manifest|export)(?:\/([^/]+))?$/);
  if (match) {
    const d = datasets.find(item => item.id === match[1]);
    if (!d || q.get("version") !== d.version) return fail("未找到演示版本", 404);
    if (match[2] === "export") return fail("纯前端预览暂不导出 30 万条数据，请使用版本清单查看演示来源。");
    if (match[2] === "manifest") return json({ scope, dataset_id: d.id, version: d.version, content_hash: "frontend-demo-not-a-persisted-hash", manifest: { schema_version: "frontend-demo.v1", provenance: "Authored synthetic UI presentation; no backend or Worker execution", seed: 42, record_count: d.record_count, split_counts: d.split_counts, generator: "apps/web/src/dev/training-center/demo.ts" } });
    if (match[2] === "overview") {
      const base = datasetOverview("success", d.kind);
      return json({ ...base, scope, dataset: d, split_counts: d.split_counts, destination_counts: Object.entries(d.split_counts).map(([key, count]) => ({ key, count, unit: d.record_unit })), source_distribution: distribution({ paper: d.record_count * .3, web: d.record_count * .3, book: d.record_count * .2, other: d.record_count * .2 }, d.record_unit, "training_record_primary_source_kind"), language_distribution: distribution({ zh: d.record_count }, d.record_unit, "training_record_language"), length_distribution: sampleLengths(d, catalog), lineage_root_ref: { catalog, type: "dataset_version", id: d.version_id } });
    }
    let start = 1, end = d.record_count;
    if (q.get("split") === "train") end = d.split_counts.train;
    if (q.get("split") === "validation") { start = d.split_counts.train + 1; end = d.split_counts.train + d.split_counts.validation; }
    if (q.get("split") === "test") start = d.split_counts.train + d.split_counts.validation + 1;
    if (match[3]) { const n = Number(match[3].split("-").at(-1)); return n >= 1 && n <= d.record_count ? json({ scope, items: [sample(d, n, catalog)], total_count: 1, offset: 0, limit: 1 }) : fail("样本不存在", 404); }
    const search = q.get("q")?.toLowerCase();
    if (search) {
      const hits: Sample[] = []; let total = 0;
      for (let n = start; n <= end; n++) { const s = sample(d, n, catalog); if (JSON.stringify(s).toLowerCase().includes(search)) { if (total >= offset && hits.length < limit) hits.push(s); total++; } }
      return json({ scope, items: hits, total_count: total, offset, limit });
    }
    return json({ scope, items: Array.from({ length: Math.max(0, Math.min(limit, end - start + 1 - offset)) }, (_, i) => sample(d, start + offset + i, catalog)), total_count: end - start + 1, offset, limit });
  }
  if (url.pathname.match(/^\/pipeline-runs\/run-demo-file-\d+\/summary$/)) {
    const run = url.pathname.split("/")[2], fileId = run.slice(4);
    const template = cases("success").processing_summary.body;
    return json({ ...template, scope, run_id: run, input_refs: [{ catalog, type: "file", id: fileId }], steps: template.steps.map(s => ({ ...s, run_id: run, input_count: 250, output_count: 250, modified_count: 38 })), totals: [{ unit: "segment", input_count: 250, output_count: 250 }] });
  }
  if (url.pathname === "/lineage/graph") {
    const root = { catalog, type: q.get("root_type") || "dataset_version", id: q.get("root_id") || datasets[0].version_id };
    const nodes = [{ id: "source", ref: { catalog, type: "source", id: "demo-source-0" }, kind: "source", label: "知识文档资料库", description: "前端演示来源", status: null, metrics: { files: 1200 }, detail: { provenance: "synthetic UI demo" } }, { id: "file", ref: { catalog, type: "file", id: "demo-file-0" }, kind: "file", label: "绿色能源发展报告.pdf", description: "章节与正文解析", status: "succeeded", metrics: { segments: 250 }, detail: {} }, { id: "root", ref: root, kind: root.type, label: datasets.find(d => d.version_id === root.id)?.name || "当前数据对象", description: "用于浏览交互的演示数据", status: "available", metrics: { records: 300000 }, detail: { provenance: "synthetic UI demo" } }];
    return json({ scope, root, nodes, edges: [{ id: "e1", source: "source", target: "file", relation: "provides" }, { id: "e2", source: "file", target: "root", relation: "included_in" }], truncated: false, truncation_reason: null });
  }
  return fail("此功能需要真实后端；当前为纯前端浏览演示。", 503);
}
