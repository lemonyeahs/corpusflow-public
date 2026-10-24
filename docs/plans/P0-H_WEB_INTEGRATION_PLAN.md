# CorpusFlow P0-H Web 前后端真实联调计划

日期：2026-10-24

## 目标与边界

P0-H 在现有 FastAPI、PostgreSQL、Celery、Redis、MinIO 和 P0-G 发布能力之上增加可运行的 TypeScript/React/Vite Web 应用。核心页面只调用真实 API；V3.1 HTML 保留在 `docs/prototype/` 和根目录作为交互参考，不直接改写。RAG、AI 采集和外部集成配置继续显示为 DEMO/未接入。

## 页面与真实 API 映射

| 页面 | 真实流程 | API |
|---|---|---|
| 登录 / 工作空间 | 开发环境身份登录、选择空间、显示角色 | `POST /auth/session`、`GET /auth/me`、`GET /workspaces` |
| 总览 | 资产统计、最近资产、任务入口 | `GET /assets/stats`、`GET /assets`、`GET /datasets`、`GET /datasets/{id}/versions` |
| 数据接入 | 文件选择、上传进度、批次登记、失败隔离 | `POST /sources`、`POST /uploads/init`、`PUT /uploads/{id}/content`、`POST /uploads/{id}/complete`、`POST /ingest-batches` |
| 原始/结构化资产 | 资产、DocumentVersion、Segment、哈希、解析状态 | `GET /assets`、`GET /assets/{id}`、`GET /documents/{id}/versions`、`GET /segments/{id}` |
| 处理中心 | 创建 N 个 Run、轮询、日志、恢复 | `POST /pipeline-runs/batches`、`GET /pipeline-runs/{id}`、`GET /pipeline-runs/{id}/logs`、`POST /pipeline-runs/{id}/resume` |
| 质量审核 | 问题、证据、审核历史和状态门控 | `GET /quality/issues`、`POST /quality/issues/{id}/reviews` |
| SFT 构建 | 预览、创建 Build、候选审核、验证 | `POST /datasets`、`POST /dataset-builds/preview`、`POST /dataset-builds`、`GET /dataset-builds/{id}/candidates`、`POST /candidate-samples/{id}/reviews`、`POST /dataset-builds/{id}/validate` |
| 发布与下载 | 版本、Manifest、签名下载 | `POST/GET /datasets/{id}/versions`、`GET /datasets/{id}/versions/{version}/manifest`、`GET /datasets/{id}/versions/{version}/download` |
| 血缘 | Asset、Segment、Sample、DatasetVersion 双向边 | `GET /lineage/{object_type}/{object_id}` |
| 系统管理 | 成员角色、审计；外部集成明确未接入 | `POST /workspaces/{wid}/members`、`GET /audit-events` |

## 当前接口差异与最小补齐

现有 OpenAPI 已覆盖核心写操作，但前端需要列表和详情来恢复刷新后的状态。P0-H 增加以下只读接口，沿用现有 workspace、身份和后端角色校验：

- `GET /sources`：当前工作空间来源列表。
- `GET /assets/{asset_id}`：资产、Blob、来源和解析状态详情。
- `GET /quality/issues`：质量问题列表，支持 `status` 筛选。
- `GET /datasets`：数据产品列表。

这些接口只返回当前 workspace 数据，不在前端复制授权规则。

## 前端数据模型

API Client 使用 `ApiError { code, message, request_id, retryable }` 统一处理错误。页面模型分别对应 `AssetSummary`、`UploadItem`、`PipelineRun`、`QualityIssue`、`DatasetBuild`、`CandidateSample`、`DatasetVersion` 和 `LineageEdge`；不使用原型的固定演示数据。会话信息仅保存开发环境返回的 token、user_id、workspace_id 和 role，页面明确标注开发认证。

## 依赖关系

登录和 workspace 选择是所有业务页面的前置条件；数据接入先创建 Source，再完成 upload init/content/complete/register；处理中心依赖已登记 Asset；质量审核依赖真实 Run/Issue；SFT 构建依赖已解析 Segment 和 training grant；发布依赖候选审核、验证和后端用途授权；下载和血缘依赖已发布版本。Vite 开发代理将 `/api` 转发到本地 FastAPI，避免把 MinIO 内部地址暴露给浏览器。

## 验证计划

1. `npm ci`、`npm run typecheck`、`npm run lint`、`npm run build`。
2. 后端 `pytest`、ruff、mypy、OpenAPI 契约和迁移回归。
3. Playwright 连接本地 Docker API、PostgreSQL、Redis、MinIO 与 Vite：登录、真实 PDF 上传、批次登记、任务轮询、结构化片段、质量门控、SFT 候选审核、发布 Manifest、签名下载、血缘和刷新恢复。
4. 使用第二个开发身份验证跨 workspace 拒绝，使用 reviewer/engineer 身份验证角色限制；桌面和窄屏各执行核心页面 smoke。

## 明确未接入

生产 OIDC、SSE、外部 WeKnora/docreader、LLM 生成、RAG 检索、AI 智能采集、Parquet 导出和正式 tokenizer 不在 P0-H 新增；页面以 DEMO 或“未接入”呈现，不伪造成功状态。
