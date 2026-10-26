import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { DashboardPage } from "../pages/DashboardPage";
import { IngestPage } from "../pages/IngestPage";
import { AssetsPage } from "../pages/AssetsPage";
import { ProcessingPage } from "../pages/ProcessingPage";
import { DatasetPage } from "../pages/DatasetPage";
import { DpoPage } from "../pages/DpoPage";
import { DocumentComparePage } from "../pages/DocumentComparePage";
import { LineagePage } from "../pages/LineagePage";
import { AdminPage } from "../pages/AdminPage";
import { useWorkspaceContext } from "./auth";
import { advancedNavigation } from "./navigation";
import { ErrorState } from "../ui";

export default function LegacyPage() {
  const ctx = useWorkspaceContext();
  const { page } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const entry = advancedNavigation.find(item => item.path === `/advanced/${page}`);
  if (!entry) return <ErrorState error={new Error("页面不存在")} />;
  if (entry.roles && !entry.roles.includes(ctx.session.role)) return <ErrorState error={new Error("没有权限访问此页面")} />;
  function legacyNavigate(value: string) {
    const [target, format] = value.split(":");
    if (advancedNavigation.some(item => item.path === `/advanced/${target}`)) navigate(`/advanced/${target}${format ? `?format=${encodeURIComponent(format)}` : ""}`);
  }
  switch (page) {
    case "dashboard": return <DashboardPage ctx={ctx} onNavigate={legacyNavigate} />;
    case "ingest": return <IngestPage ctx={ctx} onDone={() => undefined} />;
    case "assets": return <AssetsPage key={params.toString()} ctx={ctx} initialFormat={params.get("format") || ""} onSelectSegment={id => navigate(`/advanced/lineage?segment_id=${encodeURIComponent(id)}`)} onCompareAsset={id => navigate(`/advanced/document?asset_id=${encodeURIComponent(id)}`)} />;
    case "document": return <DocumentComparePage key={params.get("asset_id")} ctx={ctx} assetId={params.get("asset_id") || ""} />;
    case "processing": return <ProcessingPage ctx={ctx} />;
    case "datasets": return <DatasetPage ctx={ctx} onPublished={() => navigate("/advanced/datasets")} />;
    case "dpo": return <DpoPage ctx={ctx} />;
    case "lineage": return <LineagePage key={params.get("segment_id")} ctx={ctx} initialId={params.get("segment_id") || ""} />;
    case "admin": return <AdminPage ctx={ctx} />;
  }
}
