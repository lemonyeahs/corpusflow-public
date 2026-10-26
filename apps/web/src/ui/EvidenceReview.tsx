import { useEffect, useState } from "react";
import { api, type ApiContext } from "../api/client";

/** Reading evidence never approves it. The reviewer must explicitly confirm the displayed text. */
export function EvidenceReview({ ctx, ids, confirmed, onConfirm }: {
  ctx: ApiContext; ids: string[]; confirmed: boolean; onConfirm: (value: boolean) => void;
}) {
  const key = ids.join(",");
  const [rows, setRows] = useState<{ segment_id: string; text: string; content_hash: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setRows([]); setError(""); }, [key, ctx.workspaceId]);
  async function read() {
    setBusy(true); setError("");
    try {
      const result = [];
      for (const id of ids) result.push(await api.evidenceSegment(ctx, id));
      setRows(result);
    } catch (failure) { setRows([]); setError(failure instanceof Error ? failure.message : "来源读取失败"); }
    finally { setBusy(false); }
  }
  if (!ids.length) return null;
  return <div className="evidence-review">
    <button className="button tiny secondary" disabled={busy} onClick={() => void read()}>读取来源片段（{ids.length}）</button>
    {error && <p role="alert">{error}</p>}
    {rows.map(row => <details key={row.segment_id} open><summary>来源 {row.segment_id}</summary><pre>{row.text}</pre><small>内容哈希 {row.content_hash}</small></details>)}
    {rows.length === ids.length && <label><input type="checkbox" checked={confirmed} onChange={event => onConfirm(event.target.checked)} />我已核对上述来源片段，审核通过时一并确认来源质量</label>}
  </div>;
}
