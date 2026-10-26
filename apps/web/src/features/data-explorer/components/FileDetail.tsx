import { Descriptions, Drawer, Tabs } from "antd";
import { Link } from "react-router-dom";
import type { DatasetSummary } from "../../../contracts/training-center";
import { EmptyState, LoadingState } from "../../../ui";
import { QueryError } from "../../training-home/components/Common";
import { dateTime, objectLink, quantity, scopeLink, sourceLabels, statusLabels } from "../../training-home/components/format";
import { useFileDetail } from "../queries";
import { FileComparison } from "./ComparisonView";
import styles from "../explorer.module.css";

export function FileDetail({ id, tab, recordId, datasets, onClose, onTab }: { id: string; tab: string; recordId?: string; datasets: DatasetSummary[]; onClose: () => void; onTab: (tab: string) => void }) {
  const query = useFileDetail(id);
  const detail = query.data;
  return <Drawer open onClose={onClose} title={detail?.file.filename || "文件详情"} width={850} destroyOnClose>
    {query.isPending ? <LoadingState /> : query.error ? <QueryError error={query.error} retry={() => void query.refetch()} /> : detail && <>
      <Tabs activeKey={tab === "comparison" ? "comparison" : "detail"} onChange={onTab} items={[
        { key: "detail", label: "文件与来源", children: <><Descriptions column={1} bordered size="small" items={[
          { key: "id", label: "文件 ID", children: detail.file.id },
          { key: "format", label: "格式 / 大小", children: `${detail.file.format.toUpperCase()} / ${quantity(detail.file.size_bytes, "byte")}` },
          { key: "status", label: "处理状态", children: statusLabels[detail.file.processing_status] },
          { key: "time", label: "接入时间（UTC）", children: dateTime(detail.file.ingested_at) },
          { key: "source", label: "来源", children: `${detail.source.name} · ${sourceLabels[detail.source.kind]}` },
          { key: "author", label: "作者 / 授权", children: `${detail.source.author || "未提供"} / ${detail.source.license || "未提供"}` },
          { key: "url", label: "来源地址", children: detail.source.url || "未提供" },
        ]} /><h3>关联训练数据集</h3>{!detail.dataset_refs.length ? <EmptyState description="暂无关联数据集" /> : <ul className={styles.related}>{detail.dataset_refs.map(ref => {
          const dataset = datasets.find(item => ref.catalog === detail.scope.catalog && item.version_id === ref.id);
          return <li key={`${ref.catalog}:${ref.id}`}><Link to={dataset ? scopeLink(`/datasets/${dataset.kind}`, detail.scope, { dataset_id: dataset.id, version: dataset.version }) : objectLink(ref, detail.scope)}>{dataset ? `${dataset.name} · ${dataset.version}` : `数据集版本 ${ref.id}`} ↗</Link></li>;
        })}</ul>}</> },
        { key: "comparison", label: "清洗前后对比", children: <FileComparison detail={detail} recordId={recordId} /> },
      ]} />
      <div className={styles.detailActions}><Link className={styles.textLink} to={objectLink({ catalog: detail.scope.catalog, type: "file", id }, detail.scope)}>查看文件血缘 ↗</Link>{detail.scope.catalog === "workspace" && <Link className={styles.textLink} to={`/advanced/document?asset_id=${encodeURIComponent(id)}`}>打开原文对照 ↗</Link>}</div>
    </>}
  </Drawer>;
}
