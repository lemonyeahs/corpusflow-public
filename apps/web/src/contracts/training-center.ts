/** Public imports. Wire DTOs are generated from the canonical Pydantic models. */
export * from "./training-center.generated";
import type { CatalogQuery, ExportQuery, FileFormat, FilesQuery, FilesResponse, SamplesQuery, TrainingKind } from "./training-center.generated";
export const FORMATS = ["all", "pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl", "other"] as const;
export const TRAINING_KINDS = ["cpt", "sft", "dpo"] as const;
export type DataFormat = FileFormat | "all";
export type ExportFormat = NonNullable<ExportQuery["export_format"]>;
export type Paginated<T> = Omit<FilesResponse, "items"> & { items: T[] };
export type CatalogParams = CatalogQuery;
export type PaginationParams = Pick<FilesQuery, "offset" | "limit">;
export type FileFilters = FilesQuery;
export type SampleFilters = SamplesQuery;
export const PRODUCT_TYPE: Record<TrainingKind, "pretrain" | "sft" | "dpo"> = { cpt: "pretrain", sft: "sft", dpo: "dpo" };
