import { useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { LineageEdge } from "../types";
import { Badge, Card, Empty, ErrorBox, Field, Page } from "../components";

export function LineagePage({ ctx, initialId }: { ctx: ApiContext; initialId?: string }) {
  const [type, setType] = useState("Asset"); const [id, setId] = useState(initialId ?? ""); const [edges, setEdges] = useState<LineageEdge[]>([]); const [error, setError] = useState("");
  async function search() { if (!id.trim()) return; setError(""); try { setEdges((await api.lineage(ctx, type, id.trim())).edges); } catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "血缘查询失败"); } }
  return <Page title="数据血缘追踪" subtitle="从 Asset、Segment、Sample 或 DatasetVersion 查询真实 lineage edge。"><Card title="查询对象"><div className="form-grid"><Field label="对象类型"><select value={type} onChange={e => setType(e.target.value)}><option>Asset</option><option>DocumentVersion</option><option>Segment</option><option>CandidateSample</option><option>DatasetVersion</option><option>PipelineRun</option></select></Field><Field label="对象 ID"><input value={id} onChange={e => setId(e.target.value)} placeholder="粘贴真实 ID" /></Field></div><button className="button primary" onClick={() => void search()}>查询血缘</button>{error && <ErrorBox message={error} />}</Card><Card title={`关联边 · ${edges.length}`}>{edges.length ? <div className="lineage-list">{edges.map((edge, index) => <div className="lineage-edge" key={`${edge.from_id}-${edge.to_id}-${index}`}><div><Badge value={edge.from_type} /><code>{edge.from_id}</code></div><strong>→ {edge.relation} →</strong><div><Badge value={edge.to_type} /><code>{edge.to_id}</code></div></div>)}</div> : <Empty>输入对象 ID 后查看正向或反向追踪结果。</Empty>}</Card></Page>;
}
