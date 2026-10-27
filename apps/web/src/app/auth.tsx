import { DEMO_MODE, demoSession } from "./demo-mode";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { api, ApiError, type ApiContext } from "../api/client";
import type { Session, Workspace } from "../types";
import { LoginPage } from "../pages/LoginPage";
import { ErrorState, LoadingState } from "../ui";
import { createQueryClient } from "./query";

export const SESSION_STORAGE_KEY = "corpusflow.p0h.session";
function stored(): Session | null {
  if (DEMO_MODE) return demoSession;
  try {
    const value: unknown = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || "null");
    if (!value || typeof value !== "object") return null;
    const s = value as Session;
    return typeof s.token === "string" && !!s.token && typeof s.workspace_id === "string" && !!s.workspace_id
      && typeof s.user_id === "string" && ["admin", "engineer", "reviewer", "viewer"].includes(s.role) ? s : null;
  } catch { return null; }
}
interface AuthValue { session: Session | null; login: (session: Session) => void; logout: () => void }
const AuthContext = createContext<AuthValue | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(stored);
  function login(next: Session) { if (DEMO_MODE) { setSession(demoSession); return; } localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(next)); setSession(next); }
  function logout() { if (DEMO_MODE) { window.location.hash = "/home?catalog=workspace"; return; } localStorage.removeItem(SESSION_STORAGE_KEY); setSession(null); }
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === SESSION_STORAGE_KEY || event.key === null) setSession(stored()); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  return <AuthContext.Provider value={{ session, login, logout }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth requires AuthProvider");
  return value;
}
const WorkspaceContext = createContext<(ApiContext & { session: Session; workspaces: Workspace[]; switchWorkspace: (id: string) => void }) | null>(null);
export function useWorkspaceContext() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspaceContext requires an authenticated workspace route");
  return value;
}
export function LoginRoute() {
  const { session, login } = useAuth();
  const [params] = useSearchParams();
  const target = params.get("returnTo") || "/home";
  const safeTarget = target.startsWith("/") && !target.startsWith("//") && !target.startsWith("/login") ? target : "/home";
  if (session) return <Navigate to={safeTarget} replace />;
  return <div className="legacy-page"><LoginPage onLogin={login} /></div>;
}
export function RequireAuth() {
  const { session } = useAuth();
  const location = useLocation();
  if (!session) return <Navigate to={`/login?returnTo=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <SessionQueries key={`${session.user_id}:${session.workspace_id}:${session.token}`} session={session} />;
}
function SessionQueries({ session }: { session: Session }) {
  const [client] = useState(createQueryClient);
  useEffect(() => () => { void client.cancelQueries(); client.clear(); }, [client]);
  return <QueryClientProvider client={client}><VerifiedWorkspace session={session} /></QueryClientProvider>;
}
function VerifiedWorkspace({ session }: { session: Session }) {
  const { login, logout } = useAuth();
  const ctx = useMemo(() => ({ token: session.token, workspaceId: session.workspace_id }), [session]);
  const me = useQuery({ queryKey: ["session", session.user_id, session.workspace_id], queryFn: async () => {
    const [identity, active] = await Promise.all([api.me(ctx), api.workspaces(ctx)]);
    return { user_id: identity.user_id, workspaces: active.items };
  } });
  const membership = me.data?.workspaces.find(w => w.workspace_id === session.workspace_id);
  if (me.isPending) return <div className="training-center-shell"><LoadingState label="正在验证工作空间…" /></div>;
  if (me.error) return <div className="training-center-shell"><ErrorState error={me.error} onRetry={() => void me.refetch()} /><button onClick={logout}>重新登录</button></div>;
  if (!membership || me.data?.user_id !== session.user_id) return <div className="training-center-shell"><ErrorState error={new ApiError(403, { error: { code: "WORKSPACE_FORBIDDEN", message: "当前身份无法访问此工作空间" } })} /><button onClick={logout}>重新登录</button></div>;
  const verifiedSession = { ...session, role: membership.role };
  return <WorkspaceContext.Provider value={{ ...ctx, session: verifiedSession, workspaces: me.data.workspaces, switchWorkspace: id => {
    const next = me.data.workspaces.find(w => w.workspace_id === id);
    if (next && id !== session.workspace_id) login({ ...session, workspace_id: id, role: next.role });
  } }}><Outlet /></WorkspaceContext.Provider>;
}
