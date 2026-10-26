import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "antd";
import { ApiError } from "../../../api/client";
import { useWorkspaceContext } from "../../../app/auth";
import { trainingKeys } from "../../../app/query";
import type { ComparisonResponse, FileDetailResponse } from "../../../contracts/training-center";
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
  const client = useQueryClient();
  const { scope, file } = detail;
  const query = useQuery({
    queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "file-comparison", { file_id: file.id, record_id: recordId }),
    queryFn: async ({ signal }) => {
      if (scope.catalog === "workspace" && !detail.processing_summary_ref) return null;
      // The file adapter owns the persisted file -> run -> step -> record mapping.
      // A record ID alone does not prove file ownership; never pick a step in the browser.
      const path = `/training-center/files/${encodeURIComponent(file.id)}/comparison`;
      const comparison = await scopedRequest<ComparisonResponse>(`${path}?${queryString({ catalog: scope.catalog, revision: scope.revision, record_id: recordId })}`, ctx, scope.catalog, scope.revision, signal, { expectedScope: scope, client });
      if (comparison.before.record_id !== comparison.after.record_id || (recordId && comparison.before.record_id !== recordId)
        || comparison.record_ref.id !== comparison.before.record_id
        || (scope.catalog === "workspace" && comparison.processing_run_ref.id !== detail.processing_summary_ref?.id)) {
        throw new ApiError(409, { error: { code: "RECORD_MISMATCH", message: "返回的对比与当前文件的处理记录不一致。" } });
      }
      return comparison;
    },
  });
  if (query.isPending) return <LoadingState label="正在加载已有处理对比…" />;
  if (query.error instanceof ApiError && query.error.code === "COMPARISON_NOT_AVAILABLE") return <EmptyState description="暂无清洗对比" />;
  if (query.error) return <QueryError error={query.error} retry={() => void query.refetch()} />;
  return query.data ? <ComparisonView comparison={query.data} /> : <EmptyState description="暂无清洗对比" />;
}
