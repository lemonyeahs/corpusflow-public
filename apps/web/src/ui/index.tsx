import { useState, type ReactNode } from "react";
import { Alert, Button, Dropdown, Empty, Spin } from "antd";
import type { ExportFormat, Metric } from "../contracts/training-center";
import styles from "./shared.module.css";
import { ApiError } from "../api/client";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return <header className={styles.header}><div><p className={styles.eyebrow}>TRAINING DATA CENTER</p><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions}</header>;
}
export function Panel({ title, extra, children }: { title?: string; extra?: ReactNode; children: ReactNode }) {
  return <section className={styles.panel}>{(title || extra) && <div className={styles.panelHead}><h2>{title}</h2>{extra}</div>}{children}</section>;
}
export function MetricCard({ title, metric }: { title: string; metric: Metric }) {
  return <Panel title={title}><div className={styles.metric}>{metric.value === null ? "暂无统计" : metric.value.toLocaleString("zh-CN")} <small>{metric.unit}</small></div></Panel>;
}
export function ChartFrame({ title, measure, unit, children }: { title: string; measure: string; unit: string; children: ReactNode }) {
  return <Panel title={title} extra={<small>{measure} · {unit}</small>}><div className={styles.chart}>{children}</div></Panel>;
}
export function LoadingState({ label = "正在加载…" }: { label?: string }) { return <div className={styles.state} role="status"><Spin /><p>{label}</p></div>; }
export function EmptyState({ description = "暂无数据" }: { description?: string }) { return <div className={styles.state}><Empty description={description} /></div>; }
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const status = error instanceof ApiError ? error.status : undefined;
  const message = status === 401 ? "登录已失效" : status === 403 ? "没有访问权限" : status === 503 ? "数据服务暂不可用" : "请求未完成";
  const detail = error instanceof Error ? error.message : "请求失败，请重试";
  return <Alert type="error" showIcon message={message} description={<>{detail === message ? null : detail}{error instanceof ApiError && error.requestId && <p>请求编号：{error.requestId}</p>}</>} action={onRetry && status !== 401 && status !== 403 && <Button onClick={onRetry}>重试</Button>} />;
}
export function ExportMenu({ onExport, disabled = false, busy = false }: { onExport: (format: ExportFormat) => void; disabled?: boolean; busy?: boolean }) {
  const [open, setOpen] = useState(false);
  const formats: ExportFormat[] = ["jsonl", "markdown", "csv", "txt"];
  return <Dropdown trigger={["click"]} open={open && !disabled && !busy} onOpenChange={setOpen} disabled={disabled || busy} menu={{ items: formats.map(key => ({ key, label: key === "markdown" ? "Markdown" : key.toUpperCase() })), onClick: ({ key }) => { setOpen(false); onExport(key as ExportFormat); } }}><Button disabled={disabled} loading={busy}>导出数据</Button></Dropdown>;
}
