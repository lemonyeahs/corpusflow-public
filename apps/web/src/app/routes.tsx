import { lazy } from "react";
import { Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { LoginRoute, RequireAuth, useWorkspaceContext } from "./auth";
import { Shell } from "./Shell";
import { DataRoute, DatasetsRoute, HomePage, IngestionPage, LineagePage } from "./modules";
import { ENGINEERS } from "./navigation";
import { EmptyState, PageHeader } from "../ui";

const LegacyPage = lazy(() => import("./LegacyPage"));
function IngestRoute() {
  const { session } = useWorkspaceContext();
  const [params] = useSearchParams();
  if (params.get("catalog") !== "workspace") {
    const next = new URLSearchParams(params); next.set("catalog", "workspace"); next.delete("revision");
    return <Navigate to={`/ingest?${next}`} replace />;
  }
  return ENGINEERS.includes(session.role) ? <IngestionPage /> : <><PageHeader title="没有访问权限" /><EmptyState description="数据接入需要管理员或工程师角色。" /></>;
}
export function AppRoutes() {
  return <Routes><Route path="/login" element={<LoginRoute />} /><Route element={<RequireAuth />}><Route element={<Shell />}>
    <Route index element={<Navigate to="/home" replace />} />
    <Route path="home" element={<HomePage />} /><Route path="data/:format" element={<DataRoute />} />
    <Route path="ingest" element={<IngestRoute />} /><Route path="datasets/:kind" element={<DatasetsRoute />} />
    <Route path="lineage" element={<LineagePage />} /><Route path="advanced/:page" element={<LegacyPage />} />
    <Route path="*" element={<><PageHeader title="页面不存在" /><EmptyState description="请从导航选择页面。" /></>} />
  </Route></Route></Routes>;
}
