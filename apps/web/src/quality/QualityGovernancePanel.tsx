import { useEffect, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import { Badge, Card, Empty, ErrorBox, Field, Loading } from "../components";
import type { QualityComparison, QualityCoverage, QualityReportData, QualityRules } from "../types";

function failure(error: unknown) { return error instanceof ApiError ? `${error.code}：${error.message}` : String(error); }
function JsonDetail({ title, value }: { title: string; value: unknown }) {
  return <details><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
export function QualityGovernancePanel({ ctx, onLineage }: { ctx: ApiContext; onLineage?: (id: string) => void }) {
  const [coverage, setCoverage] = useState<QualityCoverage>();
  const [rules, setRules] = useState<QualityRules>();
  const [report, setReport] = useState<QualityReportData>();
  const [comparison, setComparison] = useState<QualityComparison>();
  const [history, setHistory] = useState<Array<{ evaluation_id: string; quality_status: string; created_at: string }>>([]);
  const [target, setTarget] = useState("");
  const [targetType, setTargetType] = useState<"dataset_build" | "dataset_version">("dataset_version");
  const [ruleId, setRuleId] = useState("");
  const [left, setLeft] = useState(""); const [right, setRight] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [newVersion, setNewVersion] = useState("2.0.0");
  const [metricKey, setMetricKey] = useState("document.metadata_completeness");
  const [threshold, setThreshold] = useState("1");
  const [enabled, setEnabled] = useState(true);
  const [sourceFilter, setSourceFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");
  async function refresh() {
    setBusy(true); setError("");
    try {
      const [c, r, h] = await Promise.all([api.qualityCoverage(ctx), api.qualityRules(ctx), api.qualityEvaluations(ctx)]);
      setCoverage(c); setRules(r); setHistory(h.items); setRuleId(r.versions[0]?.id ?? "");
    } catch (err) { setError(failure(err)); } finally { setBusy(false); }
  }
  useEffect(() => { setReport(undefined); setComparison(undefined); void refresh(); }, [ctx.workspaceId]);
  async function action(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); } catch (err) { setError(failure(err)); } finally { setBusy(false); }
  }
  async function evaluate() {
    setReport(undefined);
    const result = await api.evaluateQuality(ctx, { target_type: targetType, target_id: target.trim(), rule_version_id: ruleId || undefined, idempotency_key: crypto.randomUUID() });
    const persisted = await api.qualityEvaluation(ctx, result.evaluation_id);
    setReport(persisted.report);
    setHistory((await api.qualityEvaluations(ctx)).items);
  }
  async function filterCoverage() {
    const params = new URLSearchParams();
    if (sourceFilter) params.set("source_id", sourceFilter);
    if (productFilter) params.set("product_type", productFilter);
    setCoverage(await api.qualityCoverage(ctx, params.toString()));
  }
  async function exportReport() {
    if (!report) return;
    // Fetch the persisted, authorized record again rather than exporting stale screen state.
    const value = await api.qualityEvaluation(ctx, report.evaluation_id);
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `quality-${report.evaluation_id}.json`; link.click(); URL.revokeObjectURL(url);
  }
  return <>
    {error && <ErrorBox message={error} />}
    {busy && <Loading />}
    <Card title="质量规则管理">
      <p className="muted">规则变更创建不可变版本。用途授权、证据、审核和快照一致性始终独立检查。</p>
      <div className="quality-controls">
        <Field label="评估规则版本"><select value={ruleId} onChange={e => setRuleId(e.target.value)}>{rules?.versions.map(v => <option key={v.id} value={v.id}>{v.version} · {v.config_hash.slice(0, 10)}</option>)}</select></Field>
        <Field label="新规则版本"><input value={newVersion} onChange={e => setNewVersion(e.target.value)} /></Field>
        <Field label="规则指标"><select value={metricKey} onChange={e => setMetricKey(e.target.value)}>{Object.keys(rules?.versions[0]?.rules ?? {}).map(key => <option key={key}>{key}</option>)}</select></Field>
        <Field label="阈值（留空仅统计）"><input type="number" min="0" step="0.01" value={threshold} onChange={e => setThreshold(e.target.value)} /></Field>
        <Field label="启用检测"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /></Field>
        <button className="button secondary" disabled={busy || !rules} onClick={() => void action(async () => { await api.createQualityRuleVersion(ctx, { version: newVersion, rules: { [metricKey]: { enabled, threshold: threshold === "" ? null : Number(threshold), manual_review: false } } }); await refresh(); })}>保存规则新版本</button>
      </div>
    </Card>
    <Card title="真实质量评估">
      <div className="quality-controls">
        <Field label="评估对象"><select value={targetType} onChange={e => setTargetType(e.target.value as typeof targetType)}><option value="dataset_version">已发布版本</option><option value="dataset_build">构建快照</option></select></Field>
        <Field label="评估目标 ID"><input value={target} onChange={e => setTarget(e.target.value)} placeholder="DatasetVersion / Build ID" /></Field>
        <button className="button" disabled={busy || !target.trim()} onClick={() => void action(evaluate)}>执行真实评估</button>
      </div>
      <Field label="历史评估"><select value="" onChange={e => { const id = e.target.value; if (id) void action(async () => setReport((await api.qualityEvaluation(ctx, id)).report)); }}><option value="">从数据库读取已完成报告</option>{history.map(item => <option key={item.evaluation_id} value={item.evaluation_id}>{item.created_at} · {item.quality_status} · {item.evaluation_id.slice(0, 8)}</option>)}</select></Field>
      {report ? <>
        <div className="metric-grid"><div className="metric-card"><span>质量结果</span><strong data-testid="quality-status">{report.quality_status}</strong><small>执行完成不等于质量通过</small></div><div className="metric-card"><span>用途授权</span><strong>{report.authorization_gate}</strong><small>独立硬门控</small></div><div className="metric-card"><span>样本规模</span><strong>{report.sample_count}</strong><small>{report.product_type} · 规则 {report.rule_version}</small></div><div className="metric-card"><span>未评估维度</span><strong>{report.unassessed.length}</strong><small>无标注不推断满分</small></div></div>
        <div className="table-wrap"><table><thead><tr><th>指标 / 方法</th><th>实际值</th><th>分子 / 分母</th><th>状态</th></tr></thead><tbody>{report.metrics.map(m => <tr key={m.metric_id}><td>{m.metric_id}<small>{m.method}</small></td><td>{m.value === null ? "—" : m.value.toFixed(4)} {m.unit}</td><td>{m.numerator ?? "—"} / {m.denominator ?? "—"}</td><td><Badge value={m.status} /></td></tr>)}</tbody></table></div>
        <JsonDetail title="门控、数据配比与目标偏差" value={{ gates: report.gates, composition: report.composition }} />
        <JsonDetail title="处理前后数量与算子记录" value={report.processing_records} />
        <JsonDetail title="完整机器可读报告与证据" value={report} />
        <div className="toolbar"><button className="button secondary" onClick={() => void action(exportReport)}>导出质量 JSON</button>{report.inputs.slice(0, 10).map(input => <button key={input.segment_id} className="link-button" onClick={() => onLineage?.(input.segment_id)}>片段血缘 {input.segment_id.slice(0, 8)}</button>)}</div>
      </> : <Empty>尚未选择评估报告。历史记录和新评估均来自 PostgreSQL。</Empty>}
    </Card>
    <Card title="领域覆盖与真实分布">
      <div className="quality-controls"><Field label="来源筛选"><input value={sourceFilter} onChange={e => setSourceFilter(e.target.value)} placeholder="Source ID，可留空" /></Field><Field label="产品类型筛选"><select value={productFilter} onChange={e => setProductFilter(e.target.value)}><option value="">全部登记资产</option>{["sft", "pretrain", "rag", "evaluation"].map(value => <option key={value}>{value}</option>)}</select></Field><button className="button secondary" disabled={busy} onClick={() => void action(filterCoverage)}>更新覆盖分析</button></div>
      {coverage ? <><p>去重资产：{coverage.asset_count} · {coverage.denominator}</p><p className="muted">整个专业领域知识覆盖率：NOT_EVALUATED。以下仅统计已登记资产。</p>{Object.keys(coverage.domain_unique_assets).length ? Object.entries(coverage.domain_unique_assets).map(([label, count]) => <div className="quality-bar" key={label}><span>{label}</span><meter min="0" max={coverage.asset_count || 1} value={count} /><span>{count} 份 / 标签出现 {coverage.domain_label_occurrences[label]} 次</span></div>) : <Empty>筛选范围内没有领域标签。</Empty>}<JsonDetail title="格式、来源、资料类型、年份、质量与用途分布" value={coverage} /></> : <Empty>尚未加载覆盖统计。</Empty>}
    </Card>
    <Card title="不可变版本差异比较">
      <div className="quality-controls"><Field label="左侧版本 ID"><input value={left} onChange={e => setLeft(e.target.value)} /></Field><Field label="右侧版本 ID"><input value={right} onChange={e => setRight(e.target.value)} /></Field><button className="button" disabled={busy || !left || !right} onClick={() => void action(async () => { setComparison(undefined); setComparison(await api.compareQualityVersions(ctx, { left_version_id: left, right_version_id: right })); })}>比较发布版本</button></div>
      {comparison ? <><div className="metric-grid">{Object.entries(comparison.comparison.counts).map(([key, count]) => <div className="metric-card" key={key}><span>{key}</span><strong>{count}</strong></div>)}</div><p>质量指标：<strong>{comparison.comparison.quality_comparison}</strong> {comparison.comparison.quality_reason}</p><p>Token 差值：{comparison.comparison.token_count_delta ?? "不可比较"} · 样本差值：{comparison.comparison.sample_count_delta}</p><JsonDetail title="样本、配置、Manifest、来源与领域变化" value={comparison.comparison} /></> : <Empty>选择同一数据产品的两个发布版本；比较不会修改版本。</Empty>}
    </Card>
  </>;
}
