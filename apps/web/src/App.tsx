import { useMemo, useState } from "react";
import { Activity, Boxes, Database, FileInput, GitBranch, LayoutDashboard, LogOut, Menu, Settings2, X } from "lucide-react";
import type { ApiContext } from "./api/client";
import type { Session } from "./types";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IngestPage } from "./pages/IngestPage";
import { AssetsPage } from "./pages/AssetsPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { DatasetPage } from "./pages/DatasetPage";
import { LineagePage } from "./pages/LineagePage";
import { AdminPage } from "./pages/AdminPage";
import { DocumentComparePage } from "./pages/DocumentComparePage";
import { DpoPage } from "./pages/DpoPage";
import { BrandLogo } from "./components/BrandLogo";
import "./styles.css";

const STORAGE_KEY = "corpusflow.p0h.session";
type PageKey = "dashboard" | "ingest" | "assets" | "processing" | "datasets" | "dpo" | "lineage" | "document" | "admin";
const nav: Array<{ key: PageKey; label: string; group: string; icon: typeof LayoutDashboard; roles?: string[] }> = [
  { key: "dashboard", label: "总览", group: "数据资产", icon: LayoutDashboard },
  { key: "ingest", label: "数据接入", group: "数据资产", icon: FileInput, roles: ["admin", "engineer"] },
  { key: "assets", label: "资产中心", group: "数据资产", icon: Boxes },
  { key: "document", label: "文档对照", group: "数据资产", icon: Boxes },
  { key: "processing", label: "处理中心", group: "数据加工", icon: Activity, roles: ["admin", "engineer"] },
  { key: "lineage", label: "数据血缘", group: "数据加工", icon: GitBranch },
  { key: "datasets", label: "SFT 数据集", group: "数据产品", icon: Database, roles: ["admin", "engineer"] },
  { key: "dpo", label: "DPO 偏好数据集", group: "数据产品", icon: Database, roles: ["admin", "engineer", "reviewer"] },
  { key: "admin", label: "系统管理", group: "平台管理", icon: Settings2, roles: ["admin"] },
];

function stored(): Session | null { try { const value = localStorage.getItem(STORAGE_KEY); return value ? JSON.parse(value) as Session : null; } catch { return null; } }

export default function App() {
  const [session, setSession] = useState<Session | null>(stored); const [page, setPage] = useState<PageKey>("dashboard"); const [mobileOpen, setMobileOpen] = useState(false); const [lineageId, setLineageId] = useState(""); const [documentId, setDocumentId] = useState(""); const [assetFormat, setAssetFormat] = useState("");
  const ctx = useMemo<ApiContext | null>(() => session ? { token: session.token, workspaceId: session.workspace_id } : null, [session]);
  function login(value: Session) { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); setSession(value); setPage("dashboard"); }
  function logout() { localStorage.removeItem(STORAGE_KEY); setSession(null); }
  function navigate(value: string) { const [target, filter] = value.split(":"); if (nav.some(item => item.key === target)) { setPage(target as PageKey); if (target === "assets") setAssetFormat(filter || ""); } setMobileOpen(false); }
  if (!session || !ctx) return <LoginPage onLogin={login} />;
  const current = nav.find(item => item.key === page) ?? nav[0];
  const content = page === "dashboard" ? <DashboardPage ctx={ctx} onNavigate={navigate} /> : page === "ingest" ? <IngestPage ctx={ctx} onDone={() => undefined} /> : page === "assets" ? <AssetsPage ctx={ctx} initialFormat={assetFormat} onSelectSegment={id => { setLineageId(id); navigate("lineage"); }} onCompareAsset={id => { setDocumentId(id); navigate("document"); }} /> : page === "document" ? <DocumentComparePage ctx={ctx} assetId={documentId} /> : page === "processing" ? <ProcessingPage ctx={ctx} /> : page === "datasets" ? <DatasetPage ctx={ctx} onPublished={() => navigate("datasets")} /> : page === "dpo" ? <DpoPage ctx={ctx} /> : page === "lineage" ? <LineagePage ctx={ctx} initialId={lineageId} /> : <AdminPage ctx={ctx} />;
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen ? "open" : ""}`}><div className="sidebar-head"><div className="sidebar-brand"><BrandLogo compact /><small>P0-H 工作台</small></div><button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label="关闭菜单"><X size={18} /></button></div><nav>{nav.filter(item => !item.roles || item.roles.includes(session.role)).map((item, index, visible) => { const Icon = item.icon; const previous = visible[index - 1]; return <div key={item.key}>{(!previous || previous.group !== item.group) && <div className="nav-group-label">{item.group}</div>}<button className={page === item.key ? "nav-item active" : "nav-item"} onClick={() => navigate(item.key)}><Icon size={17} /><span>{item.label}</span></button></div>; })}</nav><div className="sidebar-foot"><div className="dev-flag">开发身份 · {session.role}</div><button className="nav-item" onClick={logout}><LogOut size={17} /><span>退出</span></button></div></aside>{mobileOpen && <button className="backdrop mobile-only" onClick={() => setMobileOpen(false)} aria-label="关闭导航" /> }<div className="main-shell"><header className="topbar"><button className="icon-button mobile-only" onClick={() => setMobileOpen(true)} aria-label="打开菜单"><Menu size={20} /></button><div><strong>{current.label}</strong><span className="topbar-path">/ {session.workspace_id.slice(0, 12)}</span></div><div className="topbar-user"><span>{session.user_id}</span><span className="role-pill">{session.role}</span></div></header>{content}<footer className="footer">玄知大模型 P0-H · 真实 API 联调 · 真实词法检索 · 本地向量可配置 · 证据回答需单独授权</footer></div></div>;
}
