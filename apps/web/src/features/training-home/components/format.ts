import type { DataFormat, ObjectRef, Scope, Unit } from "../../../contracts/training-center";
import { queryString } from "../api";

export const unitLabels: Record<Unit, string> = { file: "个文件", segment: "个片段", record: "条", article: "篇", pair: "对", byte: "B", token: "Tokens", ratio: "%" };
export const sourceLabels: Record<string, string> = { web: "网页", book: "书籍", paper: "论文", other: "其他", unknown: "未知" };
export const statusLabels: Record<string, string> = { unprocessed: "未处理", queued: "排队中", running: "处理中", succeeded: "已完成", partial: "部分完成", failed: "失败" };
export const formatLabels: Record<DataFormat, string> = { all: "全部格式", pdf: "PDF 文档", html: "HTML 网页", md: "Markdown", txt: "TXT 文本", docx: "Word 文档", csv: "CSV 表格", json: "JSON 数据", jsonl: "JSONL 数据", other: "其他格式" };
export function quantity(value: number | null | undefined, unit: Unit) {
  if (value == null) return "暂无统计";
  if (unit === "ratio") return `${(value * 100).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}%`;
  if (unit === "byte") {
    const level = Math.min(3, Math.floor(Math.log(Math.max(value, 1)) / Math.log(1024)));
    return `${(value / 1024 ** level).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} ${["B", "KB", "MB", "GB"][level]}`;
  }
  return value.toLocaleString("zh-CN");
}
export function dateTime(value: string | null) {
  return value ? new Intl.DateTimeFormat("zh-CN", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "暂无时间";
}
export function scopeLink(path: string, scope: Pick<Scope, "catalog" | "revision">, extra: object = {}) {
  return `${path}?${queryString({ catalog: scope.catalog, revision: scope.revision, ...extra })}`;
}
export function objectLink(ref: ObjectRef, scope: Scope) {
  // Snapshot revisions belong to a catalog, so never copy one across catalogs.
  return `/lineage?${queryString({ catalog: ref.catalog, revision: ref.catalog === scope.catalog ? scope.revision : undefined, root_type: ref.type, root_id: ref.id })}`;
}
