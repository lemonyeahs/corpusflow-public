import { lazy, Suspense } from "react";
import { Alert, Button, Input, Pagination, Select, Table, Tag } from "antd";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { PageHeader, Panel, EmptyState, LoadingState } from "../../ui";
import { FORMATS, type DataFormat, type FileSummary, type ProcessingStatus, type SourceKind } from "../../contracts/training-center";
import { useCatalogScope } from "../../app/catalog";
import { CatalogControls, DataFlow, MetricGrid, QueryError, ScopeNote, isExpired } from "../training-home/components/Common";
import { dateTime, formatLabels, objectLink, quantity, scopeLink, sourceLabels, statusLabels, unitLabels } from "../training-home/components/format";
import { useDatasets, useFiles, useFormatStats } from "./queries";
import { FileDetail } from "./components/FileDetail";
import styles from "./explorer.module.css";

const StatisticsCharts = lazy(() => import("./components/StatisticsCharts"));
function pageNumber(value: string | null, fallback: number, max = Number.MAX_SAFE_INTEGER) {
  return value && /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) ? Math.min(max, Number(value)) : fallback;
}
export default function DataExplorer() {
  const format = useParams().format as DataFormat;
  const [params, setParams] = useSearchParams();
  const scope = useCatalogScope();
  const source = params.get("source_kind") || undefined;
  const status = params.get("status") || undefined;
  const language = params.get("language") || undefined;
  const q = params.get("q") || "";
  const offset = pageNumber(params.get("offset"), 0);
  const limit = Math.max(1, pageNumber(params.get("limit"), 20, 100));
  const filters = { source_kind: source as SourceKind | undefined, status: status as ProcessingStatus | undefined, language };
  const files = useFiles({ ...filters, format, q, offset, limit });
  const stats = useFormatStats(format, filters);
  const datasets = useDatasets();
  function update(values: Record<string, string | number | undefined>, reset = true) {
    setParams(previous => {
      const next = new URLSearchParams(previous);
      if (reset) ["offset", "file_id", "detail_tab", "record_id"].forEach(key => next.delete(key));
      Object.entries(values).forEach(([key, value]) => value === undefined || value === "" ? next.delete(key) : next.set(key, String(value)));
      return next;
    });
  }
  const expired = [files.error, stats.error, datasets.error].find(isExpired);
  const activeScope = files.data?.scope;
  const selectedFile = params.get("file_id");
  const refs = stats.data?.dataset_refs || [];
  return <div className={styles.page}>
    <PageHeader title="数据台" description={`${formatLabels[format]} · 查看文件、处理结果和训练用途。`} />
    <div className={styles.toolbar}><CatalogControls />{activeScope && !files.error && <ScopeNote scope={activeScope} />}</div>
    <nav className={styles.formatTabs} aria-label="文件格式">{FORMATS.map(value => <Link key={value} className={value === format ? styles.active : ""} to={scopeLink(`/data/${value}`, { catalog: scope.catalog, revision: scope.revision || "" }, { source_kind: source, status, language })}>{value === "all" ? "全部格式" : value === "other" ? "其他" : value.toUpperCase()}</Link>)}</nav>
    <div className={styles.filters}>
      <Select aria-label="来源类别" placeholder="全部来源" value={source} allowClear options={Object.entries(sourceLabels).filter(([key]) => key !== "unknown").map(([value, label]) => ({ value, label }))} onChange={value => update({ source_kind: value })} />
      <Select aria-label="语言" placeholder="全部语言" value={language} allowClear options={[{ value: "zh", label: "中文" }, { value: "en", label: "英文" }]} onChange={value => update({ language: value })} />
      <Select aria-label="处理状态" placeholder="全部状态" value={status} allowClear options={Object.entries(statusLabels).map(([value, label]) => ({ value, label }))} onChange={value => update({ status: value })} />
      <Button onClick={() => update({ source_kind: undefined, language: undefined, status: undefined, q: undefined })}>清除筛选</Button>
    </div>
    {expired ? <QueryError error={expired} retry={() => void scope.refreshSnapshot()} /> : <>
      {!scope.revision ? (files.isPending ? <LoadingState label="正在确定数据快照…" /> : null) : stats.isLoading ? <LoadingState label="正在加载范围统计…" /> : stats.error ? <QueryError error={stats.error} retry={() => void stats.refetch()} /> : stats.data && <>
        <MetricGrid metrics={stats.data.metrics} items={[["file_count", "文件数量"], ["segment_count", "结构化片段"], ["size_bytes", "文件总大小"], ["quality_pass_rate", "质量通过率"]]} />
        <DataFlow flow={stats.data.flow} />
        <Suspense fallback={<LoadingState label="正在加载图表…" />}><StatisticsCharts stats={stats.data} /></Suspense>
      </>}
      <Panel title="文件列表" extra={<span className={styles.note}>按文件名、ID 稳定排序</span>}>
        <div className={styles.searchRow}><Input.Search key={q} aria-label="搜索文件名" placeholder="搜索文件名" defaultValue={q} onSearch={value => update({ q: value.trim() })} enterButton="搜索" /><span className={styles.note}>搜索仅影响文件列表；上方统计按格式、来源、语言和状态计算。</span></div>
        {files.isPending ? <LoadingState /> : files.error ? <QueryError error={files.error} retry={() => void files.refetch()} /> : <>
          <Table<FileSummary> dataSource={files.data?.items} rowKey="id" loading={files.isFetching} size="middle" pagination={false} scroll={{ x: 850 }} locale={{ emptyText: <EmptyState description="当前条件下没有文件" /> }} columns={[
            { title: "文件名", dataIndex: "filename", key: "filename", width: 260, render: (name: string, file) => <button className={styles.fileButton} onClick={() => update({ file_id: file.id, detail_tab: "detail" }, false)}><span className={styles.fileBadge}>{file.format.toUpperCase()}</span><span>{name}</span></button> },
            { title: "来源", dataIndex: "source_kind", render: (value: string) => sourceLabels[value] || value },
            { title: "大小", dataIndex: "size_bytes", render: (value: number) => quantity(value, "byte") },
            { title: "状态", dataIndex: "processing_status", render: (value: string) => <Tag color={value === "succeeded" ? "green" : value === "failed" ? "red" : value === "running" ? "blue" : "default"}>{statusLabels[value]}</Tag> },
            { title: "片段", dataIndex: "segment_count", render: (value: number | null) => value === null ? "暂无统计" : value.toLocaleString("zh-CN") },
            { title: "操作", key: "actions", render: (_, file) => <div className={styles.rowActions}><button onClick={() => update({ file_id: file.id, detail_tab: "comparison" }, false)}>对比</button>{activeScope && <Link to={objectLink({ catalog: scope.catalog, type: "file", id: file.id }, activeScope)}>血缘</Link>}</div> },
          ]} />
          <div className={styles.pagination}><span>共 {files.data?.total_count.toLocaleString("zh-CN") ?? 0} 个文件</span><Pagination current={Math.floor(offset / limit) + 1} pageSize={limit} total={files.data?.total_count || 0} showSizeChanger pageSizeOptions={[10, 20, 50, 100]} onChange={(page, size) => update({ offset: size !== limit ? 0 : (page - 1) * size, limit: size }, false)} /></div>
          {!!files.data?.total_count && offset >= files.data.total_count && <Alert type="info" message="当前页超出结果范围" action={<Button onClick={() => update({ offset: 0 }, false)}>返回第一页</Button>} />}
        </>}
      </Panel>
      <div className={styles.relatedPanel}><Panel title="关联训练数据集" extra={<small className={styles.note}>当前统计范围内的关联版本</small>}>
        {stats.error || (!scope.revision && files.error) ? <p className={styles.note}>统计加载成功后显示关联数据集。</p> : !scope.revision || stats.isPending || datasets.isPending ? <LoadingState /> : datasets.error ? <QueryError error={datasets.error} retry={() => void datasets.refetch()} /> : !refs.length ? <EmptyState description="暂无关联数据集" /> : <ul className={styles.related}>{refs.map(ref => {
          const dataset = datasets.data?.items.find(item => ref.catalog === scope.catalog && item.version_id === ref.id);
          return <li key={`${ref.catalog}:${ref.id}`}><Link to={dataset && activeScope ? scopeLink(`/datasets/${dataset.kind}`, activeScope, { dataset_id: dataset.id, version: dataset.version }) : objectLink(ref, stats.data!.scope)}>{dataset ? `${dataset.kind.toUpperCase()} · ${dataset.name} · ${dataset.version}` : `数据集版本 ${ref.id}`} ↗</Link>{dataset && <small>{quantity(dataset.record_count, dataset.record_unit)} {unitLabels[dataset.record_unit]} · 整个版本总量</small>}</li>;
        })}</ul>}
      </Panel></div>
      {activeScope && <p className={styles.note}>快照时间 {dateTime(activeScope.as_of)} UTC · 未知统计不计作零。</p>}
      {selectedFile && scope.revision && <FileDetail key={`${scope.catalog}:${scope.revision}:${selectedFile}`} id={selectedFile} tab={params.get("detail_tab") || "detail"} recordId={params.get("record_id") || undefined} datasets={datasets.data?.items || []} onClose={() => update({ file_id: undefined, detail_tab: undefined, record_id: undefined }, false)} onTab={tab => update({ detail_tab: tab }, false)} />}
    </>}
  </div>;
}
