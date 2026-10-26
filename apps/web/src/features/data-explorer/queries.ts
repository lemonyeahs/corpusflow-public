import type { DataFormat, DatasetsResponse, FileDetailResponse, FilesQuery, FilesResponse, FormatStatsResponse, StatsQuery } from "../../contracts/training-center";
import { useCatalogQuery } from "../training-home/queries";

export function useFiles(filters: FilesQuery) {
  return useCatalogQuery<FilesResponse>("files", "/training-center/files", filters, true, true);
}
export function useFormatStats(format: DataFormat, filters: StatsQuery) {
  return useCatalogQuery<FormatStatsResponse>("format-stats", `/training-center/formats/${format}/stats`, { ...filters, timezone: "UTC" });
}
export function useDatasets() {
  return useCatalogQuery<DatasetsResponse>("datasets", "/training-center/datasets");
}
export function useFileDetail(id: string | null) {
  return useCatalogQuery<FileDetailResponse>("file-detail", `/training-center/files/${encodeURIComponent(id || "")}`, {}, !!id);
}
