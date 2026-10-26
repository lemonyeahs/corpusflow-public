import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { Session } from "../types";
import { BrandLogo } from "../components/BrandLogo";

export function LoginPage({ onLogin }: { onLogin: (session: Session) => void }) {
  const [userId, setUserId] = useState("p0h-admin");
  const [displayName, setDisplayName] = useState("P0-H 管理员");
  const [workspace, setWorkspace] = useState("P0-H 联调空间");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { onLogin(await api.session({ user_id: userId.trim(), display_name: displayName.trim(), workspace_name: workspace.trim() })); }
    catch (err) { setError(err instanceof ApiError ? `${err.code}：${err.message}` : "无法连接 API"); }
    finally { setBusy(false); }
  }
  return <div className="login-shell"><div className="login-panel"><BrandLogo /><p className="eyebrow">P0-H 数据工程工作台</p><h1>数据工程工作台</h1><p className="muted">真实 API 联调环境。当前使用开发身份认证，生产环境不会接受此登录方式。</p><form onSubmit={submit} className="stack"><label className="field"><span>开发身份标识</span><input value={userId} onChange={e => setUserId(e.target.value)} required /></label><label className="field"><span>显示名称</span><input value={displayName} onChange={e => setDisplayName(e.target.value)} required /></label><label className="field"><span>工作空间</span><input value={workspace} onChange={e => setWorkspace(e.target.value)} required /></label>{error && <div className="inline-error">{error}</div>}<button className="button primary wide" disabled={busy}>{busy ? "连接中…" : "进入工作台"}</button></form><p className="login-note">身份、空间和角色由后端返回；页面不会硬编码生产 Token 或密钥。</p></div></div>;
}
