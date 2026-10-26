# 玄知大模型 Web（P0-H）

这是 玄知大模型 的 TypeScript + React + Vite Web 工作台。核心业务页面通过 `src/api/client.ts` 调用真实 FastAPI，不使用固定业务演示数据；V3.1 HTML 原型保留在 `docs/prototype/`。

## 本地启动

先启动真实后端依赖和服务：

```bash
docker compose --env-file .env -f infra/compose.yaml up -d postgres redis minio init api worker dispatcher
```

再启动 Web：

```bash
cd apps/web
npm ci
npm run dev
```

浏览器访问 <http://127.0.0.1:5173>。Vite 将 `/api` 代理到 `http://127.0.0.1:58000`；可通过 `VITE_API_BASE_URL` 指定部署后的公开反向代理地址。

## 检查与测试

```bash
npm run typecheck
npm run lint
npm run build
npm run e2e
```

`npm run e2e` 需要本地 Docker API、Worker、PostgreSQL、Redis、MinIO 和 Playwright Chromium。测试会创建隔离开发身份和 workspace，写入本地测试数据，不访问生产环境。

## 页面边界

已接入真实 API 的页面包括登录/空间、数据接入、资产和结构化片段、处理 Run、质量审核、SFT 构建、发布下载、血缘和系统审计。生产 OIDC、RAG、AI 智能采集、外部解析服务、正式模型生成和 Parquet 导出仍显示为 DEMO/未接入。
