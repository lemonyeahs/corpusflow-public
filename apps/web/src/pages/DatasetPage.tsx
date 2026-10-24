import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { CandidateSample, Dataset, DatasetProductType } from "../types";
import { Badge, Card, Empty, ErrorBox, Field, Page } from "../components";

const PURPOSES: Record<string, string> = { sft: "training", pretrain: "training", rag: "rag", evaluation: "evaluation" };

export function DatasetPage({ ctx, onPublished }: { ctx: ApiContext; onPublished: () => void }) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [productTypes, setProductTypes] = useState<DatasetProductType[]>([]);
  const [productType, setProductType] = useState("sft");
  const [selectedDataset, setSelectedDataset] = useState("");
  const [name, setName] = useState("SFT 数据产品");
  const [segmentIds, setSegmentIds] = useState("");
  const [preview, setPreview] = useState<{ included_count: number; excluded_count: number; included: Array<{ segment_id: string; reason: string }>; excluded: Array<{ segment_id: string; reason: string }> }>();
  const [build, setBuild] = useState<{ build_id: string; config_hash: string; status: string; candidate_count: number; metrics?: Record<string, unknown>; excluded?: Array<Record<string, string>> }>();
  const [candidates, setCandidates] = useState<CandidateSample[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState("1.0.0");
  const [published, setPublished] = useState("");
  const [chunkSize, setChunkSize] = useState("128");
  const [overlap, setOverlap] = useState("16");
  const [evaluationJson, setEvaluationJson] = useState("[]");

  const currentProduct = useMemo(() => datasets.find(item => item.dataset_id === selectedDataset)?.product_type || productType, [datasets, selectedDataset, productType]);
  const purpose = PURPOSES[currentProduct] || "training";
  const productLabel = currentProduct === "sft" ? "SFT" : currentProduct === "pretrain" ? "预训练" : currentProduct === "rag" ? "RAG" : "评测";
  const ids = segmentIds.split(/[\s,]+/).map(item => item.trim()).filter(Boolean);

  async function load() {
    try {
      const [datasetResult, productResult] = await Promise.all([api.datasets(ctx), api.datasetProductTypes(ctx)]);
      setDatasets(datasetResult.items);
      setProductTypes(productResult.items);
      if (!selectedDataset && datasetResult.items[0]) {
        setSelectedDataset(datasetResult.items[0].dataset_id);
        setProductType(datasetResult.items[0].product_type);
      }
    } catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "数据产品加载失败"); }
  }
  useEffect(() => { void load(); }, [ctx.workspaceId]);

  async function createDataset() {
    setBusy(true); setError("");
    try {
      const created = await api.createDataset(ctx, { name, product_type: productType });
      setDatasets(items => [created, ...items]); setSelectedDataset(created.dataset_id);
    } catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "创建数据产品失败"); }
    finally { setBusy(false); }
  }
  async function runPreview() {
    setBusy(true); setError("");
    try { setPreview(await api.preview(ctx, { product_type: currentProduct, purpose, segment_ids: ids })); }
    catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "预览失败"); }
    finally { setBusy(false); }
  }
  async function createBuild() {
    if (!selectedDataset) { setError("请先创建或选择数据产品"); return; }
    let config: Record<string, unknown> = { tokenizer_version: "builtin-whitespace-1", split_strategy: currentProduct === "rag" ? "all" : "source_group" };
    if (currentProduct === "rag") config = { ...config, unit: "tokens", chunk_size: Number(chunkSize), overlap: Number(overlap) };
    if (currentProduct === "evaluation") {
      try { config = { ...config, evaluation_samples: JSON.parse(evaluationJson) }; }
      catch { setError("评测样本必须是合法 JSON 数组"); return; }
    }
    setBusy(true); setError("");
    try {
      const created = await api.createBuild(ctx, { dataset_id: selectedDataset, segment_ids: ids, purpose, config });
      setBuild(created); setCandidates((await api.candidates(ctx, created.build_id)).items);
    } catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "构建创建失败"); }
    finally { setBusy(false); }
  }
  async function review(sample: CandidateSample, decision: "approved" | "rejected") {
    try { await api.reviewSample(ctx, sample.sample_id, { decision, note: "Web 审核" }); if (build) setCandidates((await api.candidates(ctx, build.build_id)).items); }
    catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "候选审核失败"); }
  }
  async function validate() {
    if (!build) return;
    setBusy(true); setError("");
    try { const result = await api.validateBuild(ctx, build.build_id); setBuild({ ...build, status: result.ok ? "validated" : "awaiting_review" }); }
    catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "构建验证失败"); }
    finally { setBusy(false); }
  }
  async function publish() {
    if (!build || !selectedDataset) return;
    setBusy(true); setError("");
    try { const result = await api.publish(ctx, selectedDataset, { build_id: build.build_id, version }); setPublished(result.dataset_version_id); onPublished(); }
    catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "发布失败"); }
    finally { setBusy(false); }
  }

  return <Page title="数据产品中心" subtitle="统一复用构建、审核、质量授权门控和不可变发布；每类产品使用独立 Schema。">
    <div className="stepper"><span className="active">1 产品</span><span>2 来源/片段</span><span>3 预览</span><span>4 配置构建</span><span>5 候选审核</span><span>6 校验发布</span></div>
    {error && <ErrorBox message={error} />}
    <div className="two-col">
      <Card title="数据产品与输入">
        <div className="form-grid">
          <Field label="产品类型"><select value={productType} onChange={e => { setProductType(e.target.value); setSelectedDataset(""); setBuild(undefined); }} aria-label="产品类型">{productTypes.length ? productTypes.map(item => <option key={item.product_type} value={item.product_type}>{item.product_type} · {item.description}</option>) : <><option value="sft">sft</option><option value="pretrain">pretrain</option><option value="rag">rag</option><option value="evaluation">evaluation</option></>}</select></Field>
          <Field label="已有数据产品"><select value={selectedDataset} onChange={e => { setSelectedDataset(e.target.value); const item = datasets.find(dataset => dataset.dataset_id === e.target.value); if (item) setProductType(item.product_type); }}><option value="">请选择</option>{datasets.filter(item => item.product_type === productType).map(item => <option key={item.dataset_id} value={item.dataset_id}>{item.name} · {item.product_type}</option>)}</select></Field>
        </div>
        <Field label="新产品名称"><input value={name} onChange={e => setName(e.target.value)} /></Field>
        <button className="button secondary" disabled={busy} onClick={() => void createDataset()}>创建 {productLabel} 产品</button>
        <Field label="Segment ID（逗号或换行分隔）"><textarea rows={4} value={segmentIds} onChange={e => setSegmentIds(e.target.value)} placeholder="从资产详情复制真实 segment_id" /></Field>
        {currentProduct === "rag" && <div className="form-grid"><Field label="Chunk Size（token）"><input type="number" min="1" value={chunkSize} onChange={e => setChunkSize(e.target.value)} /></Field><Field label="Overlap（token）"><input type="number" min="0" value={overlap} onChange={e => setOverlap(e.target.value)} /></Field></div>}
        {currentProduct === "evaluation" && <Field label="评测样本 JSON（question/reference/evidence_ids）"><textarea rows={7} value={evaluationJson} onChange={e => setEvaluationJson(e.target.value)} placeholder='[{"question":"...","reference_answer":"...","evidence_ids":["..."]}]' /></Field>}
        <div className="toolbar"><button className="button secondary" disabled={busy || !ids.length} onClick={() => void runPreview()}>预览授权范围</button><button className="button primary" disabled={busy || !ids.length || !selectedDataset} onClick={() => void createBuild()}>创建构建快照</button></div>
        {preview && <div className="notice"><strong>预览结果 · {currentProduct}</strong><span>纳入 {preview.included_count} · 排除 {preview.excluded_count}</span>{preview.excluded.map(item => <small key={item.segment_id}>{item.segment_id.slice(0, 12)}：{item.reason}</small>)}</div>}
      </Card>
      <Card title="候选审核与发布">
        {build ? <><div className="list-row"><div><strong>Build {build.build_id.slice(0, 12)}</strong><small>{currentProduct} · config {build.config_hash.slice(0, 12)} · {build.candidate_count} 条候选</small></div><Badge value={build.status} /></div>
          <div className="list">{candidates.map(sample => <div className="candidate" key={sample.sample_id}><div><code>{sample.sample_id}</code><small>{sample.sample_key} · {sample.payload_hash.slice(0, 12)}</small>{sample.payload && <pre>{JSON.stringify(sample.payload, null, 2).slice(0, 600)}</pre>}</div><div className="toolbar"><Badge value={sample.status} /><button className="button tiny" disabled={sample.status === "approved"} onClick={() => void review(sample, "approved")}>通过</button><button className="button tiny danger" disabled={sample.status === "rejected"} onClick={() => void review(sample, "rejected")}>驳回</button></div></div>)}</div>
          <div className="toolbar"><button className="button secondary" disabled={busy} onClick={() => void validate()}>服务端验证快照</button><Field label="版本"><input value={version} onChange={e => setVersion(e.target.value)} pattern="\\d+\\.\\d+\\.\\d+" /></Field><button className="button primary" disabled={busy || build.status !== "validated"} onClick={() => void publish()}>发布不可变版本</button></div>{published && <div className="success-box">已发布 DatasetVersion：{published}</div>}
        </> : <Empty>创建构建后，真实 CandidateSample 会出现在这里。</Empty>}
      </Card>
    </div>
  </Page>;
}
