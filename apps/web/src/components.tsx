import type { ReactNode } from "react";

export function Page({ title, subtitle, children, actions }: { title: string; subtitle?: string; children: ReactNode; actions?: ReactNode }) {
  return <main className="page"><div className="page-heading"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</div>{children}</main>;
}

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{title && <div className="card-title"><h2>{title}</h2></div>}{children}</section>;
}

export function Badge({ value }: { value: string }) {
  const tone = /succeeded|approved|published|confirmed|completed|resolved|verified/i.test(value) ? "good" : /failed|rejected|blocked|isolated|error/i.test(value) ? "bad" : /queued|running|review|pending|awaiting|uploading/i.test(value) ? "warn" : "neutral";
  return <span className={`badge ${tone}`}>{value}</span>;
}

export function Empty({ children = "暂无数据" }: { children?: ReactNode }) { return <div className="empty">{children}</div>; }
export function Loading() { return <div className="loading"><span className="spinner" />加载中…</div>; }
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="error-box"><strong>请求未完成</strong><span>{message}</span>{onRetry && <button className="button secondary" onClick={onRetry}>重试</button>}</div>; }
export function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
export function formatTime(value?: string | null) { return value ? new Date(value).toLocaleString("zh-CN") : "—"; }
