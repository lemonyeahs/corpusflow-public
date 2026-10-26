import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Table, Tag } from "antd";
import { ApiError } from "../../../api/client";
import { queryString, scopedRequest } from "../../../api/training-center";
import { useWorkspaceContext } from "../../../app/auth";
import { trainingKeys } from "../../../app/query";
import type { FileDetailResponse, ProcessingStepSummary, ProcessingSummaryResponse } from "../../../contracts/training-center";
import { EmptyState, LoadingState } from "../../../ui";
import { QueryError } from "../../training-home/components/Common";
import { dateTime, quantity, statusLabels, unitLabels } from "../../training-home/components/format";

export function FileProcessingSummary({ detail }: { detail: FileDetailResponse }) {
  const ctx = useWorkspaceContext();
  const client = useQueryClient();
  const { scope, file, processing_summary_ref: run } = detail;
  const query = useQuery({
    queryKey: trainingKeys.query(ctx.workspaceId, scope.catalog, scope.revision, "file-processing-summary", { file_id: file.id, run_id: run?.id }),
    enabled: scope.catalog === "workspace" && !!run,
    queryFn: async ({ signal }) => {
      const summary = await scopedRequest<ProcessingSummaryResponse>(`/pipeline-runs/${encodeURIComponent(run!.id)}/summary?${queryString({ catalog: "workspace", revision: scope.revision })}`, ctx, "workspace", scope.revision, signal, { expectedScope: scope, client });
      if (summary.run_id !== run!.id || !summary.input_refs.some(ref => ref.catalog === "workspace" && ref.type === "file" && ref.id === file.id)) {
        throw new ApiError(409, { error: { code: "RECORD_MISMATCH", message: "处理摘要与当前文件的运行引用不一致。" } });
      }
      return summary;
    },
  });
  if (scope.catalog !== "workspace" || !run) return <EmptyState description="暂无可关联的处理记录" />;
  if (query.isPending) return <LoadingState label="正在读取已有处理摘要…" />;
  if (query.error) return <QueryError error={query.error} retry={() => void query.refetch()} />;
  const summary = query.data!;
  return <div><p>运行 {summary.run_id} · <Tag>{statusLabels[summary.status]}</Tag></p>
    {!summary.steps.length ? <EmptyState description="尚无已记录的执行步骤" /> : <Table<ProcessingStepSummary> rowKey="id" pagination={false} size="small" scroll={{ x: 640 }} dataSource={summary.steps} columns={[
      { title: "步骤", render: (_, step) => `${step.sequence}. ${step.operator_key} · ${step.operator_version}` },
      { title: "执行次数", dataIndex: "attempt" },
      { title: "状态", dataIndex: "status", render: (status: string) => statusLabels[status] },
      { title: "输入", render: (_, step) => `${quantity(step.input_count, step.input_unit)}${step.input_count === null ? "" : unitLabels[step.input_unit]}` },
      { title: "输出", render: (_, step) => `${quantity(step.output_count, step.output_unit)}${step.output_count === null ? "" : unitLabels[step.output_unit]}` },
      { title: "完成时间（UTC）", dataIndex: "completed_at", render: (value: string | null) => dateTime(value) },
    ]} />}
    <p>运行边界统计（不累加串行步骤）</p>
    {!summary.totals.length ? <p>暂无边界统计</p> : <ul>{summary.totals.map(total => <li key={total.unit}>{unitLabels[total.unit]}：输入 {quantity(total.input_count, total.unit)} · 输出 {quantity(total.output_count, total.unit)}</li>)}</ul>}
  </div>;
}
