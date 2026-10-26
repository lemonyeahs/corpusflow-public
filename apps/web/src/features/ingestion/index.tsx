import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Progress, Select, Space, Tag, Upload } from "antd";
import { Download, FileInput, Play, RefreshCw } from "lucide-react";
import { api, BASE_URL, request } from "../../api/client";
import { useWorkspaceContext } from "../../app/auth";
import type {
  ExportFormat,
  ProcessingStepSummary,
  ProcessingSummaryResponse,
} from "../../contracts/training-center";
import { EmptyState, ErrorState, ExportMenu, LoadingState, PageHeader, Panel } from "../../ui";
import styles from "./ingestion.module.css";

type UploadStatus = "ready" | "uploading" | "registered" | "queued" | "running" | "succeeded" | "partial" | "failed";
type IngestFile = { file: File; status: UploadStatus; progress: number; uploadId?: string; assetId?: string; runId?: string; error?: string };

const terminal = new Set<UploadStatus>(["succeeded", "partial", "failed"]);
const statusLabels: Record<UploadStatus, string> = { ready: "待上传", uploading: "上传中", registered: "已登记", queued: "排队中", running: "处理中", succeeded: "已完成", partial: "部分成功", failed: "失败" };

function statusColor(status: UploadStatus): "default" | "processing" | "success" | "warning" | "error" {
  if (status === "succeeded") return "success";
  if (status === "partial") return "warning";
  if (status === "failed") return "error";
  if (status === "running" || status === "uploading") return "processing";
  return "default";
}

export default function IngestionPage() {
  const ctx = useWorkspaceContext();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<IngestFile[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [parser, setParser] = useState("builtin");
  const [selectedOperators, setSelectedOperators] = useState<string[]>(["builtin.clean", "builtin.deduplicate", "builtin.quality"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [summary, setSummary] = useState<ProcessingSummaryResponse | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const sources = useMemo(() => api.sources(ctx), [ctx]);
  const operators = useMemo(() => api.operators(ctx), [ctx]);
  const [sourceItems, setSourceItems] = useState<Awaited<typeof sources>['items']>([]);
  const [operatorItems, setOperatorItems] = useState<Awaited<typeof operators>['items']>([]);

  useEffect(() => { void sources.then(value => setSourceItems(value.items)).catch(setError); }, [sources]);
  useEffect(() => { void operators.then(value => setOperatorItems(value.items.filter(item => item.available))).catch(setError); }, [operators]);

  useEffect(() => {
    if (!activeRunId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const run = await api.run(ctx, activeRunId);
        if (cancelled) return;
        setFiles(current => current.map(item => item.runId === activeRunId ? { ...item, status: (run.status as UploadStatus) || "running", error: run.error_code || undefined } : item));
        try {
          const next = await request<ProcessingSummaryResponse>(`/pipeline-runs/${activeRunId}/summary?catalog=workspace`, ctx);
          if (!cancelled) setSummary(next);
        } catch { /* Older servers expose node details through /pipeline-runs/{id}; keep polling. */ }
        if (!terminal.has(run.status as UploadStatus) && !cancelled) window.setTimeout(() => void poll(), 1500);
      } catch (pollError) {
        if (!cancelled) setError(pollError);
      }
    };
    void poll();
    return () => { cancelled = true; };
  }, [activeRunId, ctx]);

  function choose(next: File[]) {
    setFiles(next.map(file => ({ file, status: "ready", progress: 0 })));
    setError(null);
    setSummary(null);
  }

  async function ensureSource() {
    if (sourceId) return sourceId;
    if (!sourceName.trim()) throw new Error("请先选择来源或填写新来源名称");
    const created = await api.createSource(ctx, { name: sourceName.trim(), kind: "other" });
    setSourceItems(current => [created, ...current]);
    setSourceId(created.source_id);
    return created.source_id;
  }

  async function start() {
    if (!files.length) { setError(new Error("请选择至少一个文件")); return; }
    setBusy(true); setError(null); setSummary(null);
    try {
      const selectedSource = await ensureSource();
      const uploaded: IngestFile[] = [];
      for (const item of files) {
        setFiles(current => current.map(value => value.file === item.file ? { ...value, status: "uploading", progress: 0 } : value));
        const init = await api.initUpload(ctx, { filename: item.file.name, size: item.file.size, content_type: item.file.type || "application/octet-stream" });
        const result = await api.uploadContent(ctx, init.upload_id, item.file, progress => setFiles(current => current.map(value => value.file === item.file ? { ...value, progress } : value)));
        await api.completeUpload(ctx, init.upload_id, result.sha256);
        uploaded.push({ ...item, status: "registered", progress: 100, uploadId: init.upload_id });
        setFiles(current => current.map(value => value.file === item.file ? uploaded.at(-1)! : value));
      }
      const ingest = await api.ingest(ctx, { upload_ids: uploaded.map(item => item.uploadId!), source_id: selectedSource });
      const assets = ingest.items.filter(item => item.asset_id).map(item => item.asset_id!);
      setFiles(current => current.map(item => { const match = ingest.items.find(value => value.upload_id === item.uploadId); return { ...item, status: match?.status === "failed" ? "failed" : "registered", assetId: match?.asset_id, error: match?.error_code }; }));
      if (!assets.length) return;
      const created = await api.createRuns(ctx, { asset_ids: assets, config: { parser, operators: selectedOperators.map(key => ({ key, config: {} })) } });
      const firstRun = created.accepted[0];
      setFiles(current => current.map(item => { const match = created.accepted.find(value => value.asset_id === item.assetId); return match ? { ...item, status: "queued", runId: match.run_id } : item; }));
      if (firstRun) setActiveRunId(firstRun.run_id);
    } catch (startError) {
      setError(startError);
    } finally {
      setBusy(false);
    }
  }

  async function exportRun(format: ExportFormat) {
    if (!activeRunId) return;
    setError(null);
    try {
      const response = await fetch(`${BASE_URL}/pipeline-runs/${activeRunId}/export?export_format=${format}`, { headers: { Authorization: `Bearer ${ctx.token}`, "X-Workspace-ID": ctx.workspaceId } });
      if (!response.ok) throw new Error(`导出失败（${response.status}）`);
      const blob = await response.blob();
      const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `pipeline-${activeRunId}.${format === "markdown" ? "md" : format}`; link.click(); URL.revokeObjectURL(link.href);
    } catch (exportError) { setError(exportError); }
  }

  const currentSteps: ProcessingStepSummary[] = summary?.steps || [];
  return <div className={styles.page}>
    <PageHeader title="数据接入" description="上传真实文件，查看解析与清洗的运行状态，并导出当前处理批次。" actions={<Tag icon={<FileInput size={13} />} color="blue">workspace</Tag>} />
    {error ? <ErrorState error={error} onRetry={() => setError(null)} /> : null}
    <div className={styles.grid}>
      <Panel title="01 / 选择文件" extra={<small>支持 PDF · HTML · MD · TXT · DOCX · CSV · JSON · JSONL</small>}>
        <Upload.Dragger multiple accept=".pdf,.html,.htm,.md,.markdown,.txt,.docx,.csv,.json,.jsonl" showUploadList={false} beforeUpload={file => { choose([...files.map(item => item.file), file]); return false; }}>
          <p className="ant-upload-drag-icon"><FileInput /></p><p className="ant-upload-text">拖拽文件到这里，或点击选择</p><p className="ant-upload-hint">文件会在点击“开始处理”后上传到当前工作空间。</p>
        </Upload.Dragger>
        <div className={styles.fields}><label>数据来源<Select value={sourceId || undefined} placeholder="选择已有来源" options={sourceItems.map(source => ({ value: source.source_id, label: `${source.name} · ${source.kind}` }))} onChange={setSourceId} /></label><label>新来源名称<input value={sourceName} onChange={event => setSourceName(event.target.value)} placeholder="可选" /></label></div>
        <div className={styles.fields}><label>解析器<Select value={parser} options={[{ value: "builtin", label: "按文件格式自动选择" }, { value: "ocr", label: "OCR（仅 PDF）" }, { value: "layout", label: "版面解析（仅 PDF）" }]} onChange={setParser} /></label><label>清洗算子<Select mode="multiple" value={selectedOperators} options={operatorItems.map(operator => ({ value: operator.operator_key, label: `${operator.operator_key} · ${operator.version}` }))} onChange={setSelectedOperators} /></label></div>
        {files.length > 0 && <div className={styles.fileList}>{files.map(item => <div className={styles.fileRow} key={`${item.file.name}-${item.file.lastModified}`}><div><strong>{item.file.name}</strong><small>{Math.ceil(item.file.size / 1024)} KB</small></div><div className={styles.fileStatus}><Tag color={statusColor(item.status)}>{statusLabels[item.status]}</Tag>{item.status === "uploading" && <Progress percent={item.progress} size="small" showInfo={false} />}{item.error && <small className={styles.error}>{item.error}</small>}</div></div>)}</div>}
        <input ref={inputRef} type="file" hidden multiple onChange={event => choose([...files.map(item => item.file), ...Array.from(event.target.files || [])])} />
        <Space><Button icon={<FileInput size={15} />} onClick={() => inputRef.current?.click()}>选择文件</Button><Button type="primary" icon={<Play size={15} />} loading={busy} disabled={!files.length} onClick={() => void start()}>开始处理</Button></Space>
      </Panel>
      <Panel title="02 / 处理状态" extra={activeRunId ? <code>{activeRunId}</code> : undefined}>
        {!activeRunId && !summary ? <EmptyState description="开始处理后，这里显示真实运行状态和计数。" /> : summary ? <div className={styles.steps}>{currentSteps.map(step => <Card size="small" key={step.id} className={styles.step}><div className={styles.stepHead}><strong>{step.sequence}. {step.operator_key}</strong><Tag color={statusColor(step.status as UploadStatus)}>{statusLabels[step.status as UploadStatus]}</Tag></div><div className={styles.counts}><span>输入 <b>{step.input_count ?? "—"}</b> {step.input_unit}</span><span>输出 <b>{step.output_count ?? "—"}</b> {step.output_unit}</span><span>修改 <b>{step.modified_count ?? "—"}</b></span><span>过滤 <b>{step.filtered_count ?? "—"}</b></span><span>失败 <b>{step.failed_count ?? "—"}</b></span></div></Card>)}</div> : <LoadingState label="正在读取处理状态…" />}
        {activeRunId && <div className={styles.toolbar}><Button icon={<RefreshCw size={14} />} onClick={() => setActiveRunId(value => value)} disabled={busy}>刷新状态</Button><ExportMenu onExport={format => void exportRun(format)} disabled={!summary || !["succeeded", "partial"].includes(summary.status)} /></div>}
      </Panel>
    </div>
    {summary && <Panel title="03 / 处理摘要" extra={<Tag color={summary.status === "succeeded" ? "success" : "warning"}>{summary.status}</Tag>}><div className={styles.summary}><span>文件输入 <b>{summary.totals.find(total => total.unit === "file")?.input_count ?? "—"}</b></span><span>片段输出 <b>{summary.totals.find(total => total.unit === "segment")?.output_count ?? "—"}</b></span><span>导出范围：当前处理批次</span><span><Download size={14} /> 导出前后保留来源引用</span></div></Panel>}
  </div>;
}
