/** Explicit local presentation mode. Never enabled by a query parameter or backend failure. */
export const DEMO_MODE = import.meta.env.DEV && import.meta.env.VITE_TC_DEMO === "true";
export const demoSession = { token: "frontend-demo-only", user_id: "演示体验员", workspace_id: "frontend-demo-workspace", role: "admin" as const };
