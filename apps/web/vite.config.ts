import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: { "import.meta.env.VITE_TC_DEMO": JSON.stringify(mode === "demo" ? "true" : "false") },
  server: {
    port: 5173,
    proxy: mode === "demo" ? undefined : {
      "/api": {
        target: loadEnv(mode, process.cwd(), "").API_PROXY_TARGET || "http://127.0.0.1:58000",
        changeOrigin: true,
      },
    },
  },
}));
