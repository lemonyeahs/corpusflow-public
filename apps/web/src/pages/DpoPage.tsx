import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { Dataset, DpoOverview, DpoPreference } from "../types";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Page } from "../components";

export function DpoPage({ ctx, onPublished }: { ctx: ApiContext; onPublished?: () => void }) {
  const [overview, setOverview] = useState<DpoOverview>();
  const [items, setItems] = useState<DpoPreference[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState("");
  const [choice, setChoice] = useState<"a" | "b" | "tie" | "uncertain" | "both_invalid">("a");
  const [reason, setReason] = useState("事实准确、证据充分且完整回答问题");
  const [sourceId, setSourceId] = useState("");
  const [evidenceIds, setEvidenceIds] = useState("");
  const [prompt, setPrompt] = useState("");
  const [responseA, setResponseA] = useState("");
  const [responseB, setResponseB] = useState("");
  const [sampleKey, setSampleKey] = useState("dpo-fixture-" + Date.now());
  const [requestKey, setRequestKey] = useState("dpo-import-" + Date.now());
  const [datasetId, setDatasetId] = useState("");
  const [buildId, setBuildId] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedItem = useMemo(() => items.find(item => item.preference_sample_id === selected), [items, selected]);
  const dpoDatasets = datasets.filter(dataset => dataset.product_type === "dpo");

  async function load() {
    setError("");
    try {
      const [summary, preferences, datasetResult] = await Promise.all([
        api.dpoOverview(ctx),
        api.dpoPreferences(ctx),
        api.datasets(ctx),
      ]);
      setOverview(summary);
      setItems(preferences.items);
      setDatasets(datasetResult.items);
      setDatasetId(current => current || datasetResult.items.find(item => item.product_type === "dpo")?.dataset_id || "");
      setSelected(current => current || preferences.items[0]?.preference_sample_id || "");
    } catch (err) {
      setError(err instanceof ApiError ? err.code + "：" + err.message : "DPO 数据加载失败");
    }
  }

  useEffect(() => { void load(); }, [ctx.workspaceId]);

  async function act(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try { await task(); await load(); } catch (err) {
      setError(err instanceof ApiError ? err.code + "：" + err.message : "DPO 操作未完成");
    } finally { setBusy(false); }
  }

  if (!overview && !error) return <Page title="DPO 偏好数据"><Loading /></Page>;

  return <Page title="DPO 偏好数据" subtitle="真实候选导入 → 成对标注 → 审核 → DpoBuilder → 不可变发布" actions={<button className="button secondary" onClick={() => void load()}>刷新</button>}>
    {error && <ErrorBox message={error} onRetry={() => void load()} />}
    {message && <div className="success-box">{message}</div>}
    {overview && <div className="metric-grid">{[
      ["偏好样本", overview.total],
      ["待标注", overview.statuses.pending ?? 0],
      ["已标注", overview.statuses.annotated ?? 0],
      ["存在分歧", (overview.statuses.uncertain ?? 0) + (overview.statuses.tie ?? 0)],
      ["审核通过", overview.statuses.approved ?? 0],
      ["已发布版本", overview.published_count],
    ].map(([label, value]) => <div className="metric-card" key={String(label)}><span>{label}</span><strong>{value}</strong><small>真实持久化记录</small></div>)}</div>}
    <div className="two-col">
      <Card title="导入候选回答对">
        <p className="muted">只接受自制 fixture、已有回答记录或合法来源；来源和 Segment 证据由后端校验训练用途授权。</p>
        <div className="form-grid">
          <Field label="批次幂等键"><input value={requestKey} onChange={event => setRequestKey(event.target.value)} /></Field>
          <Field label="样本键"><input value={sampleKey} onChange={event => setSampleKey(event.target.value)} /></Field>
          <Field label="Source ID"><input value={sourceId} onChange={event => setSourceId(event.target.value)} /></Field>
          <Field label="Evidence Segment ID"><input value={evidenceIds} onChange={event => setEvidenceIds(event.target.value)} placeholder="一个或多个，逗号分隔" /></Field>
        </div>
        <Field label="Prompt"><textarea value={prompt} onChange={event => setPrompt(event.target.value)} /></Field>
        <Field label="Response A"><textarea value={responseA} onChange={event => setResponseA(event.target.value)} /></Field>
        <Field label="Response B"><textarea value={responseB} onChange={event => setResponseB(event.target.value)} /></Field>
        <button className="button primary" disabled={busy || !prompt || !responseA || !responseB || !sourceId || !evidenceIds} onClick={() => void act(async () => {
          await api.importDpoPreferences(ctx, {
            request_key: requestKey,
            samples: [{ sample_key: sampleKey, prompt, response_a: responseA, response_b: responseB, source_id: sourceId, evidence_ids: evidenceIds.split(",").map(value => value.trim()).filter(Boolean) }],
          });
          setMessage("候选回答对已导入，等待独立偏好标注。");
        })}>导入候选</button>
      </Card>
      <Card title="候选与标注">
        {items.length ? <div className="list">{items.map(item => <button className={"list-row " + (selected === item.preference_sample_id ? "selected" : "")} key={item.preference_sample_id} onClick={() => setSelected(item.preference_sample_id)}><div><strong>{item.sample_key}</strong><small>{item.prompt.slice(0, 100)}</small></div><Badge value={item.status} /></button>)}</div> : <Empty>暂无偏好样本。</Empty>}
      </Card>
    </div>
    {selectedItem && <Card title={"成对偏好标注 · " + selectedItem.sample_key}>
      <p><strong>Prompt：</strong>{selectedItem.prompt}</p>
      <div className="two-col"><div className="document-code"><strong>Response A</strong><pre>{selectedItem.response_a}</pre></div><div className="document-code"><strong>Response B</strong><pre>{selectedItem.response_b}</pre></div></div>
      <p className="muted">证据：{selectedItem.evidence_ids.join(", ")} · Source：{selectedItem.source_id}</p>
      <div className="form-grid"><Field label="偏好"><select value={choice} onChange={event => setChoice(event.target.value as typeof choice)}><option value="a">A 更好</option><option value="b">B 更好</option><option value="tie">两者相当</option><option value="uncertain">无法判断</option><option value="both_invalid">两者均不合格</option></select></Field><Field label="理由"><textarea value={reason} onChange={event => setReason(event.target.value)} /></Field></div>
      <div className="toolbar"><button className="button" disabled={busy || selectedItem.status === "approved" || selectedItem.status === "rejected"} onClick={() => void act(async () => { await api.annotateDpo(ctx, selectedItem.preference_sample_id, { choice, reason }); setMessage("独立标注已保存；冲突或不确定结果不会进入 DPO 导出。"); })}>提交独立标注</button><button className="button secondary" disabled={busy || !["annotated", "uncertain", "tie"].includes(selectedItem.status) || !["a", "b"].includes(choice)} onClick={() => void act(async () => { await api.reviewDpo(ctx, selectedItem.preference_sample_id, { decision: "approved", choice: choice as "a" | "b", note: "已核对成对回答、证据和偏好理由。" }); setMessage("偏好样本已审核通过。"); })}>复核并审核通过</button><button className="button danger" disabled={busy || selectedItem.status === "rejected"} onClick={() => void act(async () => { await api.reviewDpo(ctx, selectedItem.preference_sample_id, { decision: "rejected", note: "证据或偏好关系不足，拒绝进入训练数据。" }); })}>审核拒绝</button></div>
    </Card>}
    <Card title="DpoBuilder 与发布">
      <div className="form-grid"><Field label="DPO Dataset"><select value={datasetId} onChange={event => setDatasetId(event.target.value)}><option value="">请选择或创建</option>{dpoDatasets.map(dataset => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.name}</option>)}</select></Field><Field label="版本"><input value={version} onChange={event => setVersion(event.target.value)} pattern="\\d+\\.\\d+\\.\\d+" /></Field></div>
      <div className="toolbar"><button className="button secondary" disabled={busy} onClick={() => void act(async () => { const dataset = await api.createDataset(ctx, { name: "DPO 偏好优化 Fixture", product_type: "dpo" }); setDatasetId(dataset.dataset_id); setMessage("DPO Dataset 已创建。"); })}>创建 DPO Dataset</button><button className="button primary" disabled={busy || !datasetId || !items.some(item => item.status === "approved")} onClick={() => void act(async () => { const result = await api.createDpoBuild(ctx, { dataset_id: datasetId, preference_sample_ids: items.filter(item => item.status === "approved").map(item => item.preference_sample_id), config: { split_strategy: "source", fixture: true } }); setBuildId(result.build_id); setMessage("DpoBuilder 已创建 " + result.candidate_count + " 条候选。"); })}>创建 DPO 构建</button>{buildId && <><button className="button secondary" disabled={busy} onClick={() => void act(async () => { const result = await api.validateBuild(ctx, buildId); setMessage(result.ok ? "构建快照验证通过。" : "构建仍有未通过门控的候选。"); })}>验证构建</button><button className="button primary" disabled={busy || !datasetId} onClick={() => void act(async () => { const result = await api.publish(ctx, datasetId, { build_id: buildId, version }); onPublished?.(); setMessage("DPO DatasetVersion " + result.dataset_version_id + " 已发布。"); })}>发布不可变版本</button></>}</div>
      {buildId && <p className="muted">Build ID：{buildId}。发布使用现有质量、授权、审核职责分离和 MinIO 不可变物化门控。</p>}
    </Card>
  </Page>;
}
