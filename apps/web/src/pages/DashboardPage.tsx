import { useEffect, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { Asset, Dataset } from "../types";
import { Badge, Card, Empty, ErrorBox, Loading, Page, formatTime } from "../components";

export function DashboardPage({ ctx, onNavigate }: { ctx: ApiContext; onNavigate: (page: string) => void }) {
  const [stats, setStats] = useState<{ total_assets: number; as_of: string }>();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() { setLoading(true); setError(""); try { const [s, a, d] = await Promise.all([api.stats(ctx), api.assets(ctx, 0, 5), api.datasets(ctx)]); setStats(s); setAssets(a.items); setDatasets(d.items); } catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "加载总览失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [ctx.workspaceId]);
  if (loading) return <Page title="总览"><Loading /></Page>;
  if (error) return <Page title="总览"><ErrorBox message={error} onRetry={() => void load()} /></Page>;
  return <Page title="工作台总览" subtitle={`数据来自 ${formatTime(stats?.as_of)} 的真实测量`} actions={<button className="button secondary" onClick={() => void load()}>刷新</button>}>
    <div className="metric-grid"><button className="metric-card" onClick={() => onNavigate("assets")}><span>原始资产</span><strong>{stats?.total_assets ?? 0}</strong><small>进入资产中心 →</small></button><button className="metric-card" onClick={() => onNavigate("ingest")}><span>接入动作</span><strong>上传</strong><small>选择真实文件 →</small></button><button className="metric-card" onClick={() => onNavigate("processing")}><span>异步处理</span><strong>Run</strong><small>轮询 Worker 状态 →</small></button><button className="metric-card" onClick={() => onNavigate("datasets")}><span>数据产品</span><strong>{datasets.length}</strong><small>查看构建和发布 →</small></button></div>
    <div className="two-col"><Card title="最近登记资产">{assets.length ? <div className="table-wrap"><table><thead><tr><th>文件</th><th>格式</th><th>状态</th></tr></thead><tbody>{assets.map(a => <tr key={a.asset_id}><td><button className="link-button" onClick={() => onNavigate("assets")}>{a.filename}</button></td><td>{a.format.toUpperCase()}</td><td><Badge value={a.quality_status} /></td></tr>)}</tbody></table></div> : <Empty>尚未登记资产，先去数据接入中心上传文件。</Empty>}</Card><Card title="数据产品">{datasets.length ? <div className="list">{datasets.map(d => <div className="list-row" key={d.dataset_id}><div><strong>{d.name}</strong><small>{d.product_type.toUpperCase()} · {formatTime(d.created_at)}</small></div><Badge value="可构建" /></div>)}</div> : <Empty>尚未创建 SFT 数据产品。</Empty>}</Card></div>
  </Page>;
}
