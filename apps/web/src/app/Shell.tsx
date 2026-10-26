import { Suspense, useState } from "react";
import { ConfigProvider, App as AntApp, Alert, Drawer } from "antd";
import zhCN from "antd/locale/zh_CN";
import { LogOut, Menu } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth, useWorkspaceContext } from "./auth";
import { navigation, advancedNavigation } from "./navigation";
import { LoadingState } from "../ui";
import { scopeDestination } from "./scope-navigation";
import styles from "./shell.module.css";

export function Shell() {
  const { session, workspaces, switchWorkspace } = useWorkspaceContext();
  const { logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const legacy = location.pathname.startsWith("/advanced/");
  const title = [...navigation, ...advancedNavigation].find(n => n.path === location.pathname)?.label || "训练数据中心";
  function destination(path: string) {
    return scopeDestination(path, location.pathname, new URLSearchParams(location.search));
  }
  function links(items: typeof navigation) {
    return items.filter(item => !item.roles || item.roles.includes(session.role)).map(item => {
      const Icon = item.icon;
      return <NavLink key={item.path} to={destination(item.path)} onClick={() => setMobileOpen(false)} className={({ isActive }) => `${styles.link} ${isActive || (item.path === "/data/all" && location.pathname.startsWith("/data/")) ? styles.active : ""}`}><Icon size={17} />{item.label}</NavLink>;
    });
  }
  const nav = <><div className={styles.brand}><b>玄</b><div>玄知数据<small>TRAINING CENTER</small></div></div><label className={styles.workspace}>工作空间<select aria-label="切换工作空间" value={session.workspace_id} onChange={e => {
    switchWorkspace(e.target.value);
    navigate("/home", { replace: true });
    setMobileOpen(false);
  }}>{workspaces.map(w => <option key={w.workspace_id} value={w.workspace_id}>{w.workspace_id}</option>)}</select></label><nav aria-label="主导航"><p className={styles.group}>训练数据</p>{links(navigation)}<details open={legacy || undefined}><summary className={styles.group}>高级工具</summary>{links(advancedNavigation)}</details></nav><div className={styles.user}><span>{session.user_id}</span><small>{session.role}</small><button onClick={logout}><LogOut size={16} />退出登录</button></div></>;
  return <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#168f78", colorText: "#202e3b", colorBgLayout: "#f5f7f8", borderRadius: 8, fontFamily: 'Inter,"Segoe UI","Microsoft YaHei",sans-serif' } }}><AntApp><div className={`training-center-shell ${styles.shell}`}><aside className={styles.sidebar}>{nav}</aside><Drawer title="工作区导航" placement="left" open={mobileOpen} onClose={() => setMobileOpen(false)} width={260} styles={{ body: { background: "#14252c", padding: 16 } }}><div className={styles.mobileNav}>{nav}</div></Drawer><div className={styles.main}><header className={styles.topbar}><button className={styles.menuButton} aria-label="打开菜单" onClick={() => setMobileOpen(true)}><Menu size={20} /></button><span>工作区 / <strong>{title}</strong></span><small>{session.role}</small></header><main className={legacy ? "legacy-page" : styles.content}>{!legacy && new URLSearchParams(location.search).get("scope_reset") === "1" && <Alert type="info" showIcon message="此页面将使用独立快照，请以本页统计时间为准。" />}<Suspense fallback={<LoadingState />}><Outlet /></Suspense></main></div></div></AntApp></ConfigProvider>;
}
