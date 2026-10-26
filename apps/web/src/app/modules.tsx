import { lazy, type ComponentType } from "react";
import { useParams } from "react-router-dom";
import { EmptyState, PageHeader, Panel } from "../ui";
import { FORMATS, TRAINING_KINDS } from "../contracts/training-center";

// Only these five explicit entry points are discovered. Other agents own their directories.
const entries = import.meta.glob<{ default: ComponentType }>([
  "../features/training-home/index.tsx", "../features/data-explorer/index.tsx",
  "../features/ingestion/index.tsx", "../features/training-datasets/index.tsx", "../features/lineage/index.tsx",
]);
function Placeholder({ title }: { title: string }) {
  return <><PageHeader title={title} description="工作区入口已就绪" /><Panel><EmptyState description="此模块正在建设中，业务功能将在后续阶段接入。" /></Panel></>;
}
function modulePage(name: string, title: string) {
  const entry = entries[`../features/${name}/index.tsx`];
  return entry ? lazy(entry) : () => <Placeholder title={title} />;
}
export const HomePage = modulePage("training-home", "训练数据中心");
const DataPage = modulePage("data-explorer", "数据台");
export const IngestionPage = modulePage("ingestion", "数据接入");
const DatasetsPage = modulePage("training-datasets", "训练数据集");
export const LineagePage = modulePage("lineage", "数据血缘");
export function DataRoute() {
  const { format } = useParams();
  return FORMATS.includes(format as typeof FORMATS[number]) ? <DataPage key={format} /> : <Placeholder title="不支持的数据格式" />;
}
export function DatasetsRoute() {
  const { kind } = useParams();
  return TRAINING_KINDS.includes(kind as typeof TRAINING_KINDS[number]) ? <DatasetsPage key={kind} /> : <Placeholder title="不支持的训练类型" />;
}
