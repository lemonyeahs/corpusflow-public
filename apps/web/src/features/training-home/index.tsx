import { DEMO_MODE } from "../../app/demo-mode";
import { Link } from "react-router-dom";
import { ArrowUpRight, Clock3, FilePlus2 } from "lucide-react";
import { PageHeader, Panel, LoadingState, EmptyState } from "../../ui";
import { useWorkspaceContext } from "../../app/auth";
import { useOverview } from "./queries";
import { CatalogControls, DataFlow, DatasetCards, MetricGrid, QueryError, ScopeNote } from "./components/Common";
import { dateTime, formatLabels, objectLink, scopeLink } from "./components/format";
import type { FileFormat } from "../../contracts/training-center";
import styles from "./home.module.css";

const commonFormats: FileFormat[] = ["pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl"];
export default function TrainingHome() {
  const query = useOverview();
  const { session } = useWorkspaceContext();
  const data = query.data;
  return <div className={styles.page}>
    <PageHeader title="训练数据中心" description="从原始文件到训练语料，让每一份数据有据可循。" actions={(["admin", "engineer"].includes(session.role)) && <Link className={styles.primaryLink} to={DEMO_MODE ? "/data/all?catalog=workspace" : "/ingest?catalog=workspace"}><FilePlus2 size={16} />{DEMO_MODE ? "浏览数据" : "接入数据"}</Link>} />
    <div className={styles.toolbar}><CatalogControls />{data && !query.error && <ScopeNote scope={data.scope} />}</div>
    {query.isPending ? <LoadingState /> : query.error ? <QueryError error={query.error} retry={() => void query.refetch()} /> : data && <>
      <MetricGrid metrics={data.metrics} items={[["file_count", "原始文件"], ["segment_count", "结构化片段"], ["training_record_count", "训练记录"], ["quality_pass_rate", "质量通过率"]]} />
      <div className={styles.sectionTitle}><h2>按格式浏览</h2><Link to={scopeLink("/data/all", data.scope)}>全部文件 <ArrowUpRight size={14} /></Link></div>
      <div className={styles.formats}>{commonFormats.map(format => {
        const bucket = data.formats.find(item => item.format === format);
        return <Link key={format} to={scopeLink(`/data/${format}`, data.scope)} className={styles.formatCard} data-format={format}><span className={styles.fileIcon}>{format.toUpperCase()}</span><h3>{formatLabels[format]}</h3><strong>{bucket ? bucket.file_count.toLocaleString("zh-CN") : "—"}<small>个文件</small></strong><ArrowUpRight size={15} /></Link>;
      })}</div>
      <Link className={styles.otherFormat} to={scopeLink("/data/other", data.scope)}>其他格式 · {data.formats.find(item => item.format === "other")?.file_count.toLocaleString("zh-CN") ?? "暂无统计"} 个文件 <ArrowUpRight size={13} /></Link>
      <div className={styles.sectionTitle}><h2>训练数据集</h2><span>保留版本、切分与来源关联</span></div>
      <DatasetCards datasets={data.datasets} scope={data.scope} />
      <div className={styles.bottomGrid}><DataFlow flow={data.flow} /><Panel title="最近活动" extra={<small className={styles.muted}>UTC</small>}>
        {!data.recent_activities.length ? <EmptyState description="暂无活动记录" /> : <ul className={styles.activities}>{data.recent_activities.map(activity => <li key={activity.id}><Clock3 size={16} /><Link to={objectLink(activity.ref, data.scope)}>{activity.label}<small>{dateTime(activity.occurred_at)} UTC</small></Link></li>)}</ul>}
      </Panel></div>
    </>}
  </div>;
}
