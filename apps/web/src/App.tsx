import { useMemo, useState } from "react";
import { Activity, Boxes, CheckCircle2, Database, FileInput, GitBranch, LayoutDashboard, LogOut, Menu, Settings2, ShieldCheck, X } from "lucide-react";
import type { ApiContext } from "./api/client";
import type { Session } from "./types";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IngestPage } from "./pages/IngestPage";
import { AssetsPage } from "./pages/AssetsPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { QualityPage } from "./pages/QualityPage";
import { DatasetPage } from "./pages/DatasetPage";
import { ReleasesPage } from "./pages/ReleasesPage";
import { LineagePage } from "./pages/LineagePage";
import { AdminPage } from "./pages/AdminPage";
import { CollectionPage } from "./pages/CollectionPage";
import { BlindReviewPage } from "./pages/BlindReviewPage";
import { RagPage } from "./pages/RagPage";
import { DocumentComparePage } from "./pages/DocumentComparePage";
import { DemoPage } from "./pages/DemoPage";
import { DpoPage } from "./pages/DpoPage";
import { BrandLogo } from "./components/BrandLogo";
import "./styles.css";

const STORAGE_KEY = "corpusflow.p0h.session";
type PageKey = "blind" | "collection" | "rag" | "dashboard" | "ingest" | "assets" | "processing" | "quality" | "datasets" | "dpo" | "releases" | "lineage" | "document" | "demo" | "admin";
const nav: Array<{ key: PageKey; label: string; icon: typeof LayoutDashboard; roles?: string[] }> = [
  { key: "dashboard", label: "总览", icon: LayoutDashboard },
  { key: "collection", label: "受控采集", icon: FileInput },
  { key: "ingest", label: "数据接入", icon: FileInput, roles: ["admin", "engineer"] },
  { key: "assets", label: "资产中心", icon: Boxes },
  { key: "document", label: "文档对照", icon: Boxes },
  { key: "demo", label: "交流演示", icon: LayoutDashboard },
  { key: "processing", label: "处理中心", icon: Activity, roles: ["admin", "engineer"] },
  { key: "quality", label: "质量审核", icon: ShieldCheck },
  { key: "datasets", label: "SFT 产品", icon: Database, roles: ["admin", "engineer"] },
  { key: "dpo", label: "DPO 偏好", icon: Database, roles: ["admin", "engineer", "reviewer"] },
  { key: "releases", label: "发布下载", icon: CheckCircle2 },
  { key: "lineage", label: "数据血缘", icon: GitBranch },
  { key: "blind", label: "盲评任务", icon: ShieldCheck, roles: ["admin", "reviewer"] },
  { key: "rag", label: "下游验证", icon: Activity },
  { key: "admin", label: "系统管理", icon: Settings2, roles: ["admin"] },
];

function stored(): Session | null { try { const value = localStorage.getItem(STORAGE_KEY); return value ? JSON.parse(value) as Session : null; } catch { return null; } }

export default function App() {
  const [session, setSession] = useState<Session | null>(stored); const [page, setPage] = useState<PageKey>("dashboard"); const [mobileOpen, setMobileOpen] = useState(false); const [lineageId, setLineageId] = useState(""); const [documentId, setDocumentId] = useState("");
  const ctx = useMemo<ApiContext | null>(() => session ? { token: session.token, workspaceId: session.workspace_id } : null, [session]);
  function login(value: Session) { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); setSession(value); setPage("dashboard"); }
  function logout() { localStorage.removeItem(STORAGE_KEY); setSession(null); }
  function navigate(value: string) { if (nav.some(item => item.key === value)) setPage(value as PageKey); setMobileOpen(false); }
  if (!session || !ctx) return <LoginPage onLogin={login} />;
  const current = nav.find(item => item.key === page) ?? nav[0];
  const content = page === "blind" ? <BlindReviewPage ctx={ctx} admin={session.role==="admin"} /> : page === "collection" ? <CollectionPage ctx={ctx} /> : page === "rag" ? <RagPage ctx={ctx} onLineage={id => { setLineageId(id); navigate("lineage"); }} /> : page === "dashboard" ? <DashboardPage ctx={ctx} onNavigate={navigate} /> : page === "ingest" ? <IngestPage ctx={ctx} onDone={() => undefined} /> : page === "assets" ? <AssetsPage ctx={ctx} onSelectSegment={id => { setLineageId(id); navigate("lineage"); }} onCompareAsset={id => { setDocumentId(id); navigate("document"); }} /> : page === "document" ? <DocumentComparePage ctx={ctx} assetId={documentId} /> : page === "demo" ? <DemoPage ctx={ctx} onNavigate={navigate} /> : page === "processing" ? <ProcessingPage ctx={ctx} /> : page === "quality" ? <QualityPage ctx={ctx} onLineage={id => { setLineageId(id); navigate("lineage"); }} /> : page === "datasets" ? <DatasetPage ctx={ctx} onPublished={() => navigate("releases")} /> : page === "dpo" ? <DpoPage ctx={ctx} /> : page === "releases" ? <ReleasesPage ctx={ctx} /> : page === "lineage" ? <LineagePage ctx={ctx} initialId={lineageId} /> : <AdminPage ctx={ctx} />;
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen ? "open" : ""}`}><div className="sidebar-head"><div className="sidebar-brand"><BrandLogo compact /><small>P0-H 工作台</small></div><button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label="关闭菜单"><X size={18} /></button></div><nav>{nav.filter(item => !item.roles || item.roles.includes(session.role)).map(item => { const Icon = item.icon; return <button className={page === item.key ? "nav-item active" : "nav-item"} key={item.key} onClick={() => navigate(item.key)}><Icon size={17} /><span>{item.label}</span></button>; })}</nav><div className="sidebar-foot"><div className="dev-flag">开发身份 · {session.role}</div><button className="nav-item" onClick={logout}><LogOut size={17} /><span>退出</span></button></div></aside>{mobileOpen && <button className="backdrop mobile-only" onClick={() => setMobileOpen(false)} aria-label="关闭导航" /> }<div className="main-shell"><header className="topbar"><button className="icon-button mobile-only" onClick={() => setMobileOpen(true)} aria-label="打开菜单"><Menu size={20} /></button><div><strong>{current.label}</strong><span className="topbar-path">/ {session.workspace_id.slice(0, 12)}</span></div><div className="topbar-user"><span>{session.user_id}</span><span className="role-pill">{session.role}</span></div></header>{content}<footer className="footer">玄知大模型 P0-H · 真实 API 联调 · 真实词法检索 · 本地向量可配置 · 证据回答需单独授权</footer></div></div>;
}
