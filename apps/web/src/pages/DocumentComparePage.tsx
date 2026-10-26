import { useEffect, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { LineageView } from "../types";
import { Badge, Card, Empty, ErrorBox, Loading, Page } from "../components";

export function DocumentComparePage({ ctx, assetId }: { ctx: ApiContext; assetId: string }) {
  const [view, setView] = useState<LineageView>();
  const [versionId, setVersionId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load(nextVersionId?: string) {
    if (!assetId) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.assetLineageView(ctx, assetId, nextVersionId || versionId || undefined);
      setView(result);
      setVersionId(result.selected_version_id ?? result.versions[0]?.document_version_id ?? "");
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}：${err.message}` : "文档对照加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [ctx.workspaceId, assetId]);
  const selected = view?.versions.find(item => item.document_version_id === versionId) ?? view?.versions[0];

  if (!assetId) return <Page title="PDF / Markdown / JSON 对照"><Empty>请先在资产中心选择一个真实 Asset。</Empty></Page>;
  if (loading) return <Page title="PDF / Markdown / JSON 对照"><Loading /></Page>;
  if (error || !view) return <Page title="PDF / Markdown / JSON 对照"><ErrorBox message={error || "暂无文档数据"} onRetry={() => void load()} /></Page>;

  return <Page title="PDF / Markdown / JSON 对照" subtitle="三栏内容来自同一 Asset 的真实对象存储和解析记录；定位精度以页面或 Segment 为准。">
    <Card title={view.asset.filename}><div className="detail-grid"><div><span>Asset ID</span><code>{view.asset.asset_id}</code></div><div><span>Source</span><code>{view.asset.source_name ?? view.asset.source_id}</code></div><div><span>SHA-256</span><code>{view.asset.sha256 ?? "—"}</code></div><div><span>大小</span><strong>{view.asset.byte_size ?? 0} bytes</strong></div></div>{view.versions.length > 1 && <label className="field" style={{ marginTop: 14 }}><span>DocumentVersion</span><select value={selected?.document_version_id ?? ""} onChange={event => void load(event.target.value)}>{view.versions.map(item => <option key={item.document_version_id} value={item.document_version_id}>v{item.version_no} · {item.parser_name} {item.parser_version}</option>)}</select></label>}</Card>
    <div className="document-compare-grid">
      <Card title="原始 PDF"><div className="document-meta"><Badge value={view.original.status} />{view.original.url && <span>签名链接有效 {view.original.expires_in}s</span>}</div>{view.original.url ? <iframe className="pdf-preview" title="原始 PDF" src={view.original.url} /> : <Empty>原始文件当前不可用。</Empty>}</Card>
      <Card title="解析 Markdown"><div className="document-meta"><Badge value={selected?.markdown.status ?? "NOT_AVAILABLE"} />{selected?.markdown.sha256 && <code>{selected.markdown.sha256.slice(0, 16)}…</code>}</div>{selected?.markdown.content ? <pre className="document-code">{selected.markdown.content}</pre> : <Empty>没有可用的 Markdown 中间产物；页面不会伪造内容。</Empty>}</Card>
      <Card title="结构化 JSON"><div className="document-meta"><Badge value={selected?.structured.status ?? "NOT_AVAILABLE"} />{selected?.structured.sha256 && <code>{selected.structured.sha256.slice(0, 16)}…</code>}</div>{selected?.structured.data ? <pre className="document-code">{JSON.stringify(selected.structured.data, null, 2)}</pre> : <Empty>结构化 JSON 尚不可用。</Empty>}</Card>
    </div>
    <Card title={`Segments · ${selected?.segments.length ?? 0}`}>
      {selected?.segments.length ? <div className="list">{selected.segments.map(segment => <details className="segment" key={segment.segment_id}><summary><code>{segment.segment_id}</code> · {segment.title ?? "未命名章节"} · {segment.location?.page ? `第 ${String(segment.location.page)} 页` : "位置未评估"}</summary><p>{segment.text}</p><small>质量：{segment.quality_state} · token：{segment.token_count} · hash：{segment.content_hash}</small></details>)}</div> : <Empty>该版本没有结构化片段。</Empty>}
    </Card>
  </Page>;
}
