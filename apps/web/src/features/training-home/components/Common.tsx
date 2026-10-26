import { Alert, Button, Segmented } from "antd";
import { ArrowRight, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../../../api/client";
import { useCatalogScope } from "../../../app/catalog";
import type { DatasetSummary, Flow, Metric, Scope } from "../../../contracts/training-center";
import { EmptyState, ErrorState, Panel } from "../../../ui";
import { dateTime, quantity, scopeLink, unitLabels } from "./format";
import styles from "../home.module.css";

export function CatalogControls() {
  const scope = useCatalogScope();
  return <div className={styles.actions}><Segmented aria-label="数据目录" value={scope.catalog} options={[{ value: "generated", label: "生成目录" }, { value: "workspace", label: "工作空间" }]} onChange={value => scope.changeCatalog(value as "generated" | "workspace")} /><Button aria-label="刷新数据快照" icon={<RefreshCw size={14} />} onClick={() => void scope.refreshSnapshot()}>刷新</Button></div>;
}
export function ScopeNote({ scope }: { scope: Scope }) {
  return <p className={styles.scope}>统计时间：{dateTime(scope.as_of)} UTC <span title={scope.revision}>快照：{scope.revision.slice(0, 14)}</span></p>;
}
export function isExpired(error: unknown) { return error instanceof ApiError && error.code === "SNAPSHOT_EXPIRED"; }
export function QueryError({ error, retry }: { error: unknown; retry: () => void }) {
  const { refreshSnapshot } = useCatalogScope();
  return isExpired(error) ? <Alert type="warning" showIcon message="数据快照已过期" description="刷新后会重新加载当前目录的全部统计和列表。" action={<Button onClick={() => void refreshSnapshot()}>刷新快照</Button>} /> : <ErrorState error={error} onRetry={retry} />;
}
export function MetricGrid({ metrics, items }: { metrics: Record<string, Metric>; items: Array<[string, string]> }) {
  return <div className={styles.metrics}>{items.map(([key, title]) => {
    const metric = metrics[key];
    return <section className={styles.metric} key={key} aria-label={title}><span>{title}</span><strong>{metric ? quantity(metric.value, metric.unit) : "暂无统计"}<small>{metric && metric.value !== null && !["ratio", "byte"].includes(metric.unit) ? unitLabels[metric.unit] : ""}</small></strong><p title={metric?.comparison_period ? `${metric.comparison_period.from} — ${metric.comparison_period.to}` : undefined}>{metric?.comparison_period && metric.delta != null ? `较对比周期 ${metric.delta > 0 ? "+" : ""}${metric.unit === "ratio" ? `${(metric.delta * 100).toFixed(1)} 个百分点` : quantity(metric.delta, metric.unit)}` : "按当前范围统计"}</p></section>;
  })}</div>;
}
const stageLabels: Record<string, string> = { files: "原始文件", segments: "结构化片段", cpt: "CPT 语料", sft: "SFT 指令", dpo: "DPO 偏好", training_records: "训练记录" };
export function DataFlow({ flow }: { flow: Flow }) {
  return <Panel title="数据流转" extra={<span className={styles.muted}>各阶段按自身单位计数</span>}>
    {!flow.stages.length ? <EmptyState description="暂无流转数据" /> : <div className={styles.flow}>{flow.stages.map(stage => <div className={styles.stage} key={stage.key}><span>{stageLabels[stage.key] || stage.label}</span><strong>{quantity(stage.count, stage.unit)} <small>{stage.count !== null ? unitLabels[stage.unit] : ""}</small></strong></div>)}</div>}
    <p className={styles.muted}>统计范围：{flow.scope_label}</p>
    {!flow.transitions.length && <p className={styles.muted}>暂无已记录的流转关联</p>}
    {flow.transitions.map((item, index) => <p className={styles.muted} key={index}>{stageLabels[item.from] || item.from} → {stageLabels[item.to] || item.to}{item.retention_ratio !== null && ` · 保留率 ${quantity(item.retention_ratio, "ratio")}`}</p>)}
  </Panel>;
}
export function DatasetCards({ datasets, scope }: { datasets: DatasetSummary[]; scope: Scope }) {
  return <div className={styles.datasets}>{(["cpt", "sft", "dpo"] as const).map(kind => {
    const entries = datasets.filter(item => item.kind === kind);
    return <section className={`${styles.dataset} ${styles[kind]}`} key={kind}><div className={styles.datasetTitle}><span>{kind.toUpperCase()}</span><small>{{ cpt: "持续预训练", sft: "指令微调", dpo: "偏好优化" }[kind]}</small></div>
      {entries.length ? entries.map(dataset => <Link key={`${dataset.id}:${dataset.version}`} to={scopeLink(`/datasets/${kind}`, scope, { dataset_id: dataset.id, version: dataset.version, tab: "overview" })} className={styles.datasetEntry}><h3>{dataset.name}</h3><div><strong>{quantity(dataset.record_count, dataset.record_unit)} <small>{unitLabels[dataset.record_unit]}</small></strong><span>{dataset.token_count === null ? "Tokens 暂无统计" : `${quantity(dataset.token_count, "token")} Tokens`}</span></div><footer>版本 {dataset.version}<span>查看数据集 <ArrowRight size={13} /></span></footer></Link>) : <div className={styles.noDataset}>暂无该类型数据集</div>}
    </section>;
  })}</div>;
}
