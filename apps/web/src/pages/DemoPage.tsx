import { useEffect, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { DemoCase } from "../types";
import { Badge, Card, Empty, ErrorBox, Loading, Page, formatTime } from "../components";

export function DemoPage({ ctx, onNavigate }: { ctx: ApiContext; onNavigate: (page: string) => void }) {
  const [cases, setCases] = useState<DemoCase[]>([]);
  const [asOf, setAsOf] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true); setError("");
    try { const result = await api.demoCases(ctx); setCases(result.items); setAsOf(result.as_of); }
    catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "演示案例加载失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [ctx.workspaceId]);
  if (loading) return <Page title="技术交流演示"><Loading /></Page>;
  if (error) return <Page title="技术交流演示"><ErrorBox message={error} onRetry={() => void load()} /></Page>;
  return <Page title="技术交流演示" subtitle={`只读案例索引 · ${formatTime(asOf)} · 对象均由当前 workspace 实时查询`} actions={<button className="button secondary" onClick={() => void load()}>刷新</button>}>
    <div className="notice"><strong>演示原则</strong><span>此入口只引导查看真实记录，不改变业务状态、不绕过权限、不创建样例数据。</span></div>
    <div className="two-col">{cases.map(item => <Card key={item.case_id} title={item.title}><div className="list-row"><Badge value={item.status} /><code>{item.case_id}</code></div><p className="muted">{item.description}</p><div className="list">{Object.entries(item.objects).map(([key, value]) => <div className="list-row" key={key}><span>{key}</span><code>{value ?? "MISSING"}</code></div>)}</div>{item.metrics && <details className="version-block"><summary>真实评测指标</summary><pre>{JSON.stringify(item.metrics, null, 2)}</pre></details>}<div className="toolbar"><button className="button secondary" onClick={() => onNavigate("dashboard")}>资产总览</button><button className="button secondary" onClick={() => onNavigate("assets")}>资产与对照</button><button className="button secondary" onClick={() => onNavigate("rag")}>RAG 验证</button></div><p className="muted">限制：{item.limitations.join("；")}</p></Card>)}</div>
    {!cases.length && <Empty>当前 workspace 没有可展示的真实案例。</Empty>}
  </Page>;
}
