import { useEffect, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { DashboardOverview, Source } from "../types";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Page, formatTime } from "../components";

function bytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

const labels: Record<string, string> = {
  assets: "原始资产",
  parsed_documents: "解析成功文档",
  segments: "结构化片段",
  approved_candidates: "审核通过候选",
  published_versions: "已发布版本",
};

export function DashboardPage({ ctx, onNavigate }: { ctx: ApiContext; onNavigate: (page: string) => void }) {
  const [overview, setOverview] = useState<DashboardOverview>();
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [format, setFormat] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams();
      if (sourceId) query.set("source_id", sourceId);
      if (format) query.set("file_format", format);
      const [result, sourceResult] = await Promise.all([
        api.dashboardOverview(ctx, query.toString()),
        api.sources(ctx),
      ]);
      setOverview(result);
      setSources(sourceResult.items);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}：${err.message}` : "加载数据资产总览失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [ctx.workspaceId, sourceId, format]);

  if (loading) return <Page title="工作台总览"><Loading /></Page>;
  if (error || !overview) return <Page title="工作台总览"><ErrorBox message={error || "暂无总览数据"} onRetry={() => void load()} /></Page>;

  const kpis = [
    ["原始资产", overview.raw.asset_count, "assets"],
    ["原始存储", bytes(overview.raw.total_bytes), "assets"],
    ["独立内容", overview.raw.unique_content_count, "assets"],
    ["解析成功文档", overview.parsing.parse_status.succeeded ?? 0, "processing"],
    ["结构化片段", overview.parsing.segment_count, "assets"],
    ["审核通过候选", overview.quality.candidate_status.approved ?? 0, "datasets"],
    ["SFT 样本", overview.products.sft?.samples ?? 0, "datasets"],
    ["DPO 偏好对", overview.products.dpo?.samples ?? 0, "dpo"],
  ] as const;

  return <Page title="工作台总览" subtitle={`数据资产总览 · 真实 workspace 统计 · ${formatTime(overview.as_of)} · 口径 ${overview.metric_definition_version}`} actions={<button className="button secondary" onClick={() => void load()}>刷新</button>}>
    <div className="quality-controls">
      <Field label="来源筛选"><select value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">全部来源</option>{sources.map(source => <option key={source.source_id} value={source.source_id}>{source.name}</option>)}</select></Field>
      <Field label="文件格式"><select value={format} onChange={event => setFormat(event.target.value)}><option value="">全部格式</option>{Object.keys(overview.formats).map(item => <option key={item} value={item}>{item.toUpperCase()}</option>)}</select></Field>
    </div>
    <div className="metric-grid">{kpis.map(([label, value, page]) => <button className="metric-card" key={label} onClick={() => onNavigate(page)}><span>{label}</span><strong>{value}</strong><small>查看真实记录 →</small></button>)}</div>
    <Card title="文件格式统计"><div className="format-grid">{Object.entries(overview.format_stats).map(([key, value]) => <button className="format-card" key={key} onClick={() => onNavigate(`assets:${key === "md" ? "md" : key}`)}><strong>{key.toUpperCase()}</strong><span>{value.count} 个文件 · {bytes(value.bytes)}</span><small>解析成功 {value.parse_succeeded} · 失败 {value.parse_failed}</small><small>占总数 {overview.raw.asset_count ? `${((value.count / overview.raw.asset_count) * 100).toFixed(1)}%` : "0%"}</small></button>)}</div></Card>
    <div className="two-col">
      <Card title="原始数据口径"><div className="detail-grid"><div><span>Source</span><strong>{overview.raw.source_count}</strong></div><div><span>Asset 记录</span><strong>{overview.raw.asset_count}</strong></div><div><span>物理文件</span><strong>{overview.raw.physical_file_count}</strong></div><div><span>总大小</span><strong>{bytes(overview.raw.total_bytes)}</strong></div><div><span>DocumentVersion</span><strong>{overview.parsing.document_version_count}</strong></div><div><span>Segment</span><strong>{overview.parsing.segment_count}</strong></div></div></Card>
      <Card title="文件格式分布">{Object.keys(overview.formats).length ? <div className="list">{Object.entries(overview.formats).map(([key, value]) => <div className="list-row" key={key}><span>{key.toUpperCase()}</span><strong>{value}</strong></div>)}</div> : <Empty>当前筛选范围没有文件。</Empty>}</Card>
    </div>
    <div className="two-col">
      <Card title="业务类型分布"><div className="list">{Object.entries(overview.business_types).map(([key, value]) => <div className="list-row" key={key}><span>{key === "unclassified" ? "未分类" : key === "paper" ? "论文" : "书籍"}</span><strong>{value}</strong></div>)}</div><p className="muted">业务类型只采用已登记元数据；未知内容归入未分类。</p></Card>
      <Card title="生命周期阶段"><div className="list">{overview.funnel.map(item => <div className="list-row" key={item.stage}><div><strong>{labels[item.stage] ?? item.stage}</strong><small>计数单位：{item.unit}</small></div><strong>{item.count}</strong></div>)}</div></Card>
    </div>
    <div className="two-col">
      <Card title="处理运行状态"><div className="list">{Object.entries(overview.parsing.run_status).map(([key, value]) => <div className="list-row" key={key}><Badge value={key} /><strong>{value}</strong></div>)}</div>{Object.keys(overview.parsing.failure_reasons).length > 0 && <><p className="muted">失败原因</p><div className="list">{Object.entries(overview.parsing.failure_reasons).map(([key, value]) => <div className="list-row" key={key}><code>{key}</code><strong>{value}</strong></div>)}</div></>}</Card>
      <Card title="质量与授权状态"><div className="list">{Object.entries(overview.quality.issue_status).map(([key, value]) => <div className="list-row" key={key}><Badge value={key} /><strong>{value}</strong></div>)}</div><p className="muted">授权分布按 purpose:status 统计，授权不与质量分数相互抵消。</p>{Object.entries(overview.raw.authorization).length ? <div className="list">{Object.entries(overview.raw.authorization).map(([key, value]) => <div className="list-row" key={key}><code>{key}</code><strong>{value}</strong></div>)}</div> : <Empty>暂无授权记录。</Empty>}</Card>
    </div>
    <Card title="最近数据产品版本">{overview.recent_versions.length ? <div className="table-wrap"><table><thead><tr><th>产品</th><th>类型</th><th>版本</th><th>样本数</th><th>状态</th><th>发布时间</th></tr></thead><tbody>{overview.recent_versions.map(version => <tr key={version.dataset_version_id}><td>{version.name}</td><td>{version.product_type.toUpperCase()}</td><td>{version.version}</td><td>{version.sample_count}</td><td><Badge value={version.status} /></td><td>{formatTime(version.published_at)}</td></tr>)}</tbody></table></div> : <Empty>暂无数据集版本。</Empty>}</Card>
  </Page>;
}
