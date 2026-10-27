import { DEMO_MODE } from "../../app/demo-mode";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Button, Drawer, Pagination, Tag } from "antd";
import { scopedRequest } from "../../api/training-center";
import { download, saveDownload } from "../../api/download";
import { useWorkspaceContext } from "../../app/auth";
import { useCatalogScope } from "../../app/catalog";
import { scopeDestination } from "../../app/scope-navigation";
import { trainingKeys } from "../../app/query";
import type { DatasetOverviewResponse, DatasetsResponse, Distribution, ExportFormat, ManifestResponse, Sample, SamplesResponse, Scope, TrainingKind } from "../../contracts/training-center";
import { EmptyState, ErrorState, ExportMenu, LoadingState, MetricCard, PageHeader, Panel } from "../../ui";
import { DatasetPage } from "../../pages/DatasetPage";
import { DpoPage } from "../../pages/DpoPage";
import { needsScopeRefresh } from "../training-home/components/Common";
import styles from "./datasets.module.css";

const labels = { cpt: "连续预训练", sft: "监督微调", dpo: "偏好优化" };
const units = { article: "篇", record: "条", pair: "对" };
const splitLabels = { train: "训练集", validation: "验证集", test: "测试集" };

function lineageLink(catalog: string, revision: string | null, type: string, id: string) {
  const current = new URLSearchParams({ catalog, ...(revision ? { revision } : {}) });
  return `${scopeDestination("/lineage", "/datasets", current)}&${new URLSearchParams({ root_type: type, root_id: id })}`;
}

function DistributionView({ title, data }: { title: string; data: Distribution }) {
  return <Panel title={title} extra={<small>{data.total_count.toLocaleString()} {units[data.unit as keyof typeof units] || data.unit}</small>}><div className={styles.distribution}>{data.buckets.map(bucket => <div key={bucket.key}>
    <div className={styles.row}><span>{({ web: "网页", book: "书籍", paper: "论文", other: "其他", unknown: "未知", zh: "中文", en: "英文" } as Record<string, string>)[bucket.key] || bucket.label}</span><strong>{bucket.count.toLocaleString()} <small>{bucket.ratio === null ? "—" : `${(bucket.ratio * 100).toFixed(1)}%`}</small></strong></div>
    <progress aria-label={`${title} ${bucket.label}`} max={1} value={bucket.ratio || 0} />
  </div>)}</div></Panel>;
}

function SampleBody({ sample }: { sample: Sample }) {
  if (sample.kind === "cpt") return <div className={styles.prose}>{sample.title && <h3>{sample.title}</h3>}{sample.text}</div>;
  if (sample.kind === "sft") return <ol className={styles.messages}>{sample.messages.map((message, index) => <li key={index} data-role={message.role}><Tag>{message.role}</Tag><div className={styles.prose}>{message.content}</div></li>)}</ol>;
  return <><div className={styles.prompt}><strong>Prompt</strong><div className={styles.prose}>{sample.prompt}</div></div><div className={styles.pair}><section><h3>Chosen · 优选回答</h3><div className={styles.prose}>{sample.chosen}</div></section><section><h3>Rejected · 非优选回答</h3><div className={styles.prose}>{sample.rejected}</div></section></div>{sample.preference_reason && <p>偏好原因：{sample.preference_reason}</p>}</>;
}

function SampleReferences({ sample, catalog, revision }: { sample: Sample; catalog: string; revision: string | null }) {
  return <div className={styles.references}>ID：{sample.id}<br />来源组：{sample.source_group_id}<br />
    来源：{sample.source_refs.length ? sample.source_refs.map(ref => <Link key={ref.id} to={lineageLink(catalog, revision, ref.type, ref.id)}>{ref.id} </Link>) : "暂无"}<br />
    片段：{sample.segment_refs.map(ref => ref.id).join("、") || "暂无关联"}
  </div>;
}

export default function TrainingDatasets() {
  const kind = useParams().kind as TrainingKind;
  const ctx = useWorkspaceContext();
  const client = useQueryClient();
  const scope = useCatalogScope();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "overview";
  const split = params.get("split") || "";
  const search = params.get("q") || "";
  const [searchDraft, setSearchDraft] = useState(search);
  const [exportError, setExportError] = useState<unknown>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const downloadController = useRef<AbortController | null>(null);
  useEffect(() => () => downloadController.current?.abort(), [ctx.workspaceId, scope.catalog, scope.revision]);
  const rawOffset = Number(params.get("offset") || 0);
  const offset = Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0;
  const canBuild = !DEMO_MODE && ["admin", "engineer", "reviewer"].includes(ctx.session.role);
  const baseParams = { catalog: scope.catalog, ...(scope.revision ? { revision: scope.revision } : {}) };
  function update(values: Record<string, string | null>) {
    setParams(previous => { const next = new URLSearchParams(previous); Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key)); return next; });
  }
  function path(resource: string, extra: Record<string, string> = {}) {
    return `/training-center/${resource}?${new URLSearchParams({ ...baseParams, ...extra })}`;
  }
  async function read<T extends { scope: Scope }>(resource: string, extra: Record<string, string>, signal: AbortSignal): Promise<T> {
    return scopedRequest<T>(path(resource, extra), ctx, scope.catalog, scope.revision, signal, { client });
  }
  const listing = useQuery({ queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "datasets", { kind }), queryFn: ({ signal }) => read<DatasetsResponse>("datasets", { kind }, signal), enabled: tab !== "build" });
  useEffect(() => { if (!scope.revision && listing.data?.scope.catalog === scope.catalog && listing.data.scope.workspace_id === ctx.workspaceId) scope.pinScope(listing.data.scope); }, [listing.data, scope.revision, scope.catalog, ctx.workspaceId]);
  useEffect(() => { setSearchDraft(search); }, [search]);
  const requestedId = params.get("dataset_id");
  const requestedVersion = params.get("version");
  const selected = listing.data?.items.find(d => (!requestedId || d.id === requestedId) && (!requestedVersion || d.version === requestedVersion));
  const datasetId = selected?.id || "";
  const version = selected?.version || "";
  const resource = `datasets/${encodeURIComponent(datasetId)}`;
  const sampleId = params.get("sample_id");
  const overview = useQuery({ queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "dataset-overview", { datasetId, version }), queryFn: ({ signal }) => read<DatasetOverviewResponse>(`${resource}/overview`, { version }, signal), enabled: !!scope.revision && !!selected && tab === "overview" });
  const samples = useQuery({ queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "samples", { datasetId, version, split, search, offset }), queryFn: ({ signal }) => read<SamplesResponse>(`${resource}/samples`, { version, offset: String(offset), limit: "20", ...(split ? { split } : {}), ...(search ? { q: search } : {}) }, signal), enabled: !!scope.revision && !!selected && tab === "samples" });
  const manifest = useQuery({ queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "manifest", { datasetId, version }), queryFn: ({ signal }) => read<ManifestResponse>(`${resource}/manifest`, { version }, signal), enabled: !!scope.revision && !!selected && tab === "manifest" });
  const detail = useQuery({ queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "sample-detail", { datasetId, version, sampleId }), queryFn: ({ signal }) => read<SamplesResponse>(`${resource}/samples/${encodeURIComponent(sampleId!)}`, { version }, signal), enabled: !!scope.revision && !!selected && !!sampleId && tab === "samples" });
  const error = listing.error || (tab === "samples" ? samples.error || detail.error : tab === "manifest" ? manifest.error : overview.error);
  const scopeError = [error, exportError].find(needsScopeRefresh);
  useEffect(() => { if (scopeError) downloadController.current?.abort(); }, [scopeError]);
  function refresh() { setExportError(null); void scope.refreshSnapshot(); }
  async function exportRecords(format: ExportFormat) {
    if (!scope.revision || error || scopeError) return;
    setExportBusy(true); setExportError(null);
    const controller = new AbortController(); downloadController.current = controller;
    try { const result = await download(path(`${resource}/export`, { version, export_format: format, ...(split ? { split } : {}), ...(search ? { q: search } : {}) }), ctx, `${kind}.${format === "markdown" ? "md" : format}`, controller.signal); if (!controller.signal.aborted) saveDownload(result); }
    catch (err) { if (!controller.signal.aborted) setExportError(err); }
    finally { setExportBusy(false); }
  }
  function build() {
    // One URL update: separate setSearchParams calls can overwrite each other.
    update({ tab: "build", catalog: "workspace", ...(scope.catalog !== "workspace" ? { revision: null, offset: null, dataset_id: null, version: null, sample_id: null, file_id: null, root_id: null, root_type: null, record_id: null, detail_tab: null } : {}) });
  }

  return <div className={styles.page}>
    <PageHeader title="训练数据集" description={`${kind.toUpperCase()} · ${labels[kind]}，查看版本、来源与训练样本。`} actions={<div className={styles.toolbar}><Button onClick={refresh}>刷新快照</Button>{canBuild && <Button type="primary" onClick={build}>构建 {kind.toUpperCase()}</Button>}</div>} />
    <div className={styles.toolbar}><label>数据目录 <select aria-label="数据目录" value={scope.catalog} onChange={e => { scope.changeCatalog(e.target.value as "generated" | "workspace"); setExportError(null); }}><option value="generated">生成目录</option><option value="workspace">工作空间</option></select></label><span className={styles.muted}>{listing.data && `快照时间 ${new Date(listing.data.scope.as_of).toLocaleString()}`}</span></div>
    <nav className={styles.tabs} aria-label="数据集视图">{[["overview", "概览"], ["samples", "样本浏览"], ["manifest", "版本清单"], ...(canBuild ? [["build", "构建与发布"]] : [])].map(([key, label]) => <button key={key} aria-current={tab === key ? "page" : undefined} onClick={() => key === "build" ? build() : update({ tab: key })}>{label}</button>)}</nav>
    {tab === "build" ? (canBuild && scope.catalog === "workspace" ? <div className="legacy-page" key={`${ctx.workspaceId}:${kind}`}>{kind === "dpo" ? <DpoPage ctx={ctx} onPublished={() => { void scope.refreshSnapshot(); }} /> : <DatasetPage ctx={ctx} initialProductType={kind === "cpt" ? "pretrain" : "sft"} onPublished={() => { void scope.refreshSnapshot(); }} />}</div> : <EmptyState description="构建与审核需要工作空间目录及相应角色权限。" />) : <>
      {listing.isPending && <LoadingState />}
      {(scopeError || error) && <ErrorState error={scopeError || error} onRetry={() => { if (scopeError) refresh(); else { void listing.refetch(); if (tab === "overview") void overview.refetch(); if (tab === "samples") { void samples.refetch(); if (sampleId) void detail.refetch(); } if (tab === "manifest") void manifest.refetch(); } }} />}
      {listing.data && !scopeError && <Panel title="数据集版本" extra={<span>{listing.data.items.length} 个版本</span>}>
        {listing.data.items.length ? <label>数据集与版本 <select className={styles.versionSelect} aria-label="数据集与版本" value={selected?.version_id || ""} onChange={e => { const d = listing.data.items.find(item => item.version_id === e.target.value); if (d) { update({ dataset_id: d.id, version: d.version, offset: null, sample_id: null }); setExportError(null); } }}><option value="" disabled>请选择版本</option>{listing.data.items.map(d => <option key={d.version_id} value={d.version_id}>{d.name} · {d.version} · {d.record_count.toLocaleString()} {units[d.record_unit]}</option>)}</select></label> : <EmptyState description="此目录尚无已发布的数据集版本。" />}
        {requestedId && !selected && listing.data.items.length > 0 && <EmptyState description="当前快照中找不到指定版本，请重新选择。" />}
      </Panel>}
      {selected && !scopeError && <>
        <div className={styles.metrics}><MetricCard title={`版本${kind === "dpo" ? "偏好对" : "记录"}总量`} metric={{ value: selected.record_count, unit: selected.record_unit }} /><Panel title="关联来源"><strong className={styles.sourceCount}>{selected.source_refs.length.toLocaleString()} <small>个</small></strong></Panel><MetricCard title="Tokens" metric={{ value: selected.token_count, unit: "token" }} /></div>
        <div className={styles.toolbar}><span className={styles.muted}>{DEMO_MODE ? "前端预览 · 下载与构建已停用。当前版本" : "导出当前版本"}{split ? `的${splitLabels[split as keyof typeof splitLabels] || split}` : "的全部划分"}{search ? `，搜索“${search}”` : ""}，包含筛选后的所有分页。</span><ExportMenu disabled={DEMO_MODE || !scope.revision || !!error} busy={exportBusy} onExport={format => void exportRecords(format)} /></div>
        {exportError && <ErrorState error={exportError} />}
        {tab === "overview" && (overview.isPending ? <LoadingState /> : overview.data && <><Panel title="数据划分"><div className={styles.splits}>{overview.data.destination_counts.map(item => <div key={item.key}><span>{splitLabels[item.key]}</span><strong>{item.count.toLocaleString()} <small>{units[selected.record_unit]}</small></strong></div>)}</div></Panel><div className={styles.charts}><DistributionView title="主要来源" data={overview.data.source_distribution} /><DistributionView title="语言分布" data={overview.data.language_distribution} /><DistributionView title="字符长度" data={overview.data.length_distribution} /></div><Link to={lineageLink(scope.catalog, scope.revision, "dataset_version", selected.version_id)}>查看此版本的数据血缘 →</Link></>)}
        {tab === "samples" && <Panel title="样本浏览"><form className={styles.toolbar} onSubmit={e => { e.preventDefault(); update({ q: searchDraft, offset: null, sample_id: null }); }}><label>划分 <select aria-label="样本划分" value={split} onChange={e => update({ split: e.target.value, offset: null, sample_id: null })}><option value="">全部</option>{Object.entries(splitLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><input aria-label="搜索样本" placeholder="搜索正文、对话或回答" value={searchDraft} onChange={e => setSearchDraft(e.target.value)} /><Button htmlType="submit" aria-label={"\u641c\u7d22"}>搜索</Button></form>
          {samples.isPending ? <LoadingState /> : samples.data && <>{!samples.data.items.length && <EmptyState description="当前条件下没有样本。" />}{samples.data.items.map((sample, index) => <article className={styles.sample} key={sample.id}><div className={styles.row}><button className={styles.sampleTitle} onClick={() => update({ sample_id: params.get("sample_id") === sample.id ? null : sample.id })}>#{sample.sequence} · {sample.kind === "cpt" ? sample.title || "正文" : sample.kind === "sft" ? "多轮对话" : "偏好对"}</button><span><Tag>{splitLabels[sample.split]}</Tag>{sample.char_count} 字符</span></div>{(!sampleId && index === 0) && <><SampleBody sample={sample} /><div className={styles.references}>ID：{sample.id}<br />来源组：{sample.source_group_id}<br />来源：{sample.source_refs.map(ref => ref.id).join("、") || "暂无"}<br />片段：{sample.segment_refs.map(ref => ref.id).join("、") || "暂无关联"}</div></>}</article>)}<Pagination current={Math.floor(offset / 20) + 1} pageSize={20} total={samples.data.total_count} showSizeChanger={false} showTotal={total => `共 ${total} ${units[selected.record_unit]}`} onChange={page => update({ offset: String((page - 1) * 20), sample_id: null })} /></>}
        </Panel>}
        <Drawer title="样本详情" open={tab === "samples" && !!sampleId} onClose={() => update({ sample_id: null })} width="min(850px, 100vw)" getContainer={false}>
          {detail.isPending ? <LoadingState /> : detail.error ? <ErrorState error={detail.error} onRetry={() => { if (scopeError) refresh(); else void detail.refetch(); }} /> : detail.data?.items.map(sample => <article key={sample.id}><Tag>{splitLabels[sample.split]}</Tag><span>{sample.char_count} 字符</span><SampleBody sample={sample} /><SampleReferences sample={sample} catalog={scope.catalog} revision={scope.revision} /></article>)}
        </Drawer>
        {tab === "manifest" && (manifest.isPending ? <LoadingState /> : manifest.data && <Panel title="版本清单"><p className={styles.references}>SHA-256：{manifest.data.content_hash}</p><pre className={styles.manifest}>{JSON.stringify(manifest.data.manifest, null, 2)}</pre></Panel>)}
      </>}
    </>}
  </div>;
}
