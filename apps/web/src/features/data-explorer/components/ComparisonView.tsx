import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "antd";
import { ApiError } from "../../../api/client";
import { useWorkspaceContext } from "../../../app/auth";
import { trainingKeys } from "../../../app/query";
import type { ComparisonResponse, FileDetailResponse, ProcessingSummaryResponse } from "../../../contracts/training-center";
import { EmptyState, LoadingState } from "../../../ui";
import { scopedRequest, queryString } from "../../training-home/api";
import { objectLink } from "../../training-home/components/format";
import { QueryError } from "../../training-home/components/Common";
import styles from "../explorer.module.css";

/** Shared with Agent 3 ingestion: receives a real/explicit-fixture DTO, never generates text. */
export function ComparisonView({ comparison }: { comparison: ComparisonResponse }) {
  if (comparison.before.record_id !== comparison.after.record_id) return <Alert type="error" message="对比记录不一致，无法展示" />;
  return <div><div className={styles.comparison}><section><h3>处理前</h3><pre>{comparison.before.text}</pre></section><section><h3>处理后</h3><pre>{comparison.after.text}</pre></section></div><p className={styles.note}>记录 ID：{comparison.before.record_id}</p><ul>{comparison.changes.map((change, index) => <li key={index}>{change}</li>)}</ul><Link className={styles.textLink} to={objectLink(comparison.record_ref, comparison.scope)}>查看记录血缘 ↗</Link></div>;
}

export function FileComparison({ detail, recordId }: { detail: FileDetailResponse; recordId?: string }) {
  const ctx = useWorkspaceContext();
  const { scope, file } = detail;
  const query = useQuery({
    queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "file-comparison", { file_id: file.id, record_id: recordId }),
    queryFn: async ({ signal }) => {
      let path: string;
      if (scope.catalog === "generated") path = `/training-center/files/${encodeURIComponent(file.id)}/comparison`;
      else {
        const run = detail.processing_summary_ref;
        // A batch may contain many files. Never show an arbitrary batch record as this file.
        if (!run || !recordId) return null;
        const summary = await scopedRequest<ProcessingSummaryResponse>(`/pipeline-runs/${encodeURIComponent(run.id)}/summary?${queryString({ catalog: "workspace", revision: scope.revision })}`, ctx, "workspace", scope.revision, signal);
        const step = [...summary.steps].sort((a, b) => b.sequence - a.sequence).find(item => (item.status === "succeeded" || item.status === "partial") && [...item.input_refs, ...item.output_refs].some(ref => ref.id === recordId));
        if (!step) return null;
        path = `/pipeline-runs/${encodeURIComponent(run.id)}/steps/${encodeURIComponent(step.id)}/comparison`;
      }
      const comparison = await scopedRequest<ComparisonResponse>(`${path}?${queryString({ catalog: scope.catalog, revision: scope.revision, record_id: recordId })}`, ctx, scope.catalog, scope.revision, signal);
      if (recordId && (comparison.before.record_id !== recordId || comparison.after.record_id !== recordId)) throw new ApiError(409, { error: { code: "RECORD_MISMATCH", message: "返回的对比与所选记录不一致。" } });
      return comparison;
    },
  });
  if (query.isPending) return <LoadingState label="正在加载已有处理对比…" />;
  if (query.error instanceof ApiError && query.error.code === "COMPARISON_NOT_AVAILABLE") return <EmptyState description="暂无清洗对比" />;
  if (query.error) return <QueryError error={query.error} retry={() => void query.refetch()} />;
  return query.data ? <ComparisonView comparison={query.data} /> : <EmptyState description={scope.catalog === "workspace" && detail.processing_summary_ref && !recordId ? "请从该文件的片段入口选择记录后查看对比，不能以批次中的其他记录代替。" : "暂无清洗对比"} />;
}
