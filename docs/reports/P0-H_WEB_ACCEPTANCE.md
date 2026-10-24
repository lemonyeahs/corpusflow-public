# CorpusFlow P0-H Web 前后端联调验收报告

日期：2026-10-24

基线：`97da91b`（P0-G）
范围：P0-H；本轮未进入 P0-I 或 P1。

## 交付结论

P0-H 在本地隔离 Docker 环境完成。新增的 React/Vite 工作台通过真实 FastAPI、PostgreSQL、Redis、Celery、MinIO 完成从文件上传到数据集发布、签名下载和血缘查看的核心业务联调。V3.1 HTML 原型未修改。

开发认证仍使用后端提供的隔离开发身份接口，并在页面上明确标注“仅开发环境”。生产 OIDC、RAG、AI 智能采集、外部解析服务和正式模型生成不属于本阶段交付。

## 实际修改

- 新增 `apps/web` TypeScript + React + Vite 前端，按登录、总览、数据接入、资产、处理、质量、SFT、发布、血缘和系统管理组织页面。
- 新增统一 API Client、严格 TypeScript 类型、统一错误 DTO、请求关联信息展示、上传进度、轮询、分页式列表入口、空/加载/错误状态和窄屏样式。
- 增加真实 API 只读能力：`GET /api/v1/sources`、`GET /api/v1/assets/{asset_id}`、`GET /api/v1/quality/issues`、`GET /api/v1/datasets`。这些接口均从当前 workspace 查询，并通过现有后端鉴权和角色策略执行隔离。
- 更新 `docs/api/openapi.json`、根 README、Web README 和 `.gitignore`。
- 新增真实 PDF 测试夹具 `apps/web/tests/fixtures/corpusflow-e2e.pdf`，仅用于本地端到端测试。
- 未新增数据库迁移；P0-H 复用了现有迁移 `0005_dataset_materialization` 和 P0-G 数据模型。

## 页面与 API 覆盖

| 页面 | 真实业务覆盖 | 主要 API |
|---|---|---|
| 登录 / 工作空间 | 开发身份登录、workspace 和角色显示 | `/auth/session`、`/auth/me`、`/workspaces` |
| 总览 | 资产、数据集统计 | `/assets/stats`、`/assets`、`/datasets`、`/datasets/{id}/versions` |
| 数据接入 | Source、文件上传、进度、批次登记 | `/sources`、`/uploads/*`、`/ingest-batches` |
| 资产 | Blob、哈希、DocumentVersion、Segment | `/assets`、`/assets/{id}` |
| 处理中心 | N 个独立 Run、状态轮询、日志、恢复 | `/pipeline-runs/batches`、`/pipeline-runs/{id}`、`/logs`、`/resume` |
| 质量审核 | 问题列表、证据和审核动作 | `/quality/issues`、`/quality/issues/{id}/reviews` |
| SFT 数据产品 | 预览、Build、候选审核、校验、发布 | `/datasets`、`/dataset-builds/*`、`/candidate-samples/*` |
| 发布与下载 | 版本、Manifest、签名下载 | `/datasets/{id}/versions/*` |
| 血缘 | Asset、Segment、Sample、DatasetVersion 查询 | `/lineage/{object_type}/{object_id}` |
| 系统管理 | 成员角色和审计入口 | `/workspaces/{wid}/members`、`/audit-events` |

## 启动命令

在项目根目录执行：

```bash
cp .env.example .env
docker compose --env-file .env -f infra/compose.yaml up -d postgres redis minio init api worker dispatcher
cd apps/web
npm ci
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 将 `/api` 代理到本地 FastAPI；前端不保存对象存储密钥。

## 验收证据

| 检查项 | 状态 | 实际结果 |
|---|---|---|
| 前端 TypeScript | PASS | `npm run typecheck` 通过 |
| 前端 ESLint | PASS | `npm run lint` 通过 |
| 前端生产构建 | PASS | `npm run build` 通过，Vite 产出 `dist` |
| 后端 ruff | PASS | `uv run --locked ruff check apps/api/src tests scripts` |
| 后端 mypy | PASS | `Success: no issues found in 27 source files` |
| 后端全量回归 | PASS | `23 passed, 10 warnings`（隔离 PostgreSQL/Redis/MinIO） |
| OpenAPI 契约 | PASS | `uv run --locked pytest -q tests/contract/test_openapi.py` |
| 迁移/初始化 | PASS | Compose `init` 完成，输出 `Local bucket exists; object versioning enabled`；当前迁移为 `0005_dataset_materialization` |
| P0-C～P0-F 业务回归 | PASS | `verify_business_loop.py` 输出 P0-C、P0-D、P0-E、P0-F PASS |
| Playwright 真实 Docker 联调 | PASS | `2 passed (6.3s)`，详见 [`P0-H_WEB_E2E.log`](P0-H_WEB_E2E.log) |
| 桌面/窄屏 smoke | PASS | `responsive.spec.ts` 通过，检查 390×844 无横向溢出 |
| P0-H 报告 | PASS | 本文件 |
| 生产 OIDC | NOT RUN | 当前仅有隔离开发身份接口，未连接生产身份提供商 |
| 外部 WeKnora/docreader | SKIPPED | P0-H 使用已有本地 ParserAdapter 和真实对象存储 |
| 生产环境验证 | NOT RUN | 按约束未访问生产环境 |

Playwright 主流程实际验证：

1. 通过界面创建 Source，选择真实 PDF，显示上传进度并完成登记。
2. 创建处理任务并轮询到成功，读取真实 Asset、DocumentVersion 和 Segment。
3. 使用第二个 reviewer 身份完成候选审核，验证审核人与发布职责分离。
4. 创建 SFT Build、校验并发布版本；读取 Manifest，获取短期签名下载 URL，并验证 JSONL 下载响应。
5. 查询已发布 DatasetVersion 的血缘，确认回到原始 Asset；使用另一 workspace 请求验证返回拒绝。
6. 刷新后从 API 恢复业务记录，并在窄屏视口检查主要页面布局。

Playwright 主测试通过 UI 执行核心业务；创建第二身份、授权训练用途、跨 workspace 请求和签名 URL 校验使用真实 API 请求，以覆盖后端安全边界，不使用 Mock API 或固定业务数据。

## 未接入能力与已知风险

- 登录页面是隔离开发认证，不是生产 OIDC/SSO；部署到生产前必须替换身份提供方和会话策略。
- 当前前端使用轮询同步 Run 状态，尚未接入 SSE/WebSocket。
- 本地 Compose 返回的签名 URL 可能包含容器内部的 `minio:9000` 地址；浏览器与 MinIO 不在同一网络时，需要在部署配置中设置可达的公开 MinIO endpoint，不能把永久凭据暴露给浏览器。
- `GET /assets/{asset_id}` 为 P0-H 的组合查询，当前采用逐版本/片段读取，后续需要分页和查询性能优化。
- RAG、AI 智能采集、外部 ParserAdapter、LLM 生成、Parquet 导出和生产级 tokenizer 仍显示为 DEMO/未接入，页面不会伪造成功结果。
- 本轮端到端测试在本地开发数据库留下测试记录；生产数据未访问、未修改。

## 回滚与恢复

P0-H 不新增数据库迁移。回滚 Web 代码和新增 API 路由即可恢复到 P0-G 代码基线；已创建的本地测试业务记录可在隔离开发数据库中清理。不得在生产环境直接执行清理或覆盖版本对象。

## 下一阶段依赖

P0-I 若继续，应先确定生产身份提供商、可达对象存储 endpoint、事件推送协议和分页契约，再补齐正式前端认证、实时状态、下载域名配置、无障碍检查、浏览器矩阵和更大规模数据集性能测试。P0-H 已停止，不自动进入下一阶段。
