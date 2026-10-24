# CorpusFlow P0-I 系统级验收与工程质量加固报告

日期：2026-10-24

基线：P0-H `9dcd81d`；本轮只做 P0-I，本地提交，不执行远程 push。

## 结论

**CONDITIONAL PASS：满足开发/演示环境 P0 退出门禁。**

核心 API、Web、PostgreSQL、Redis、MinIO、Worker 和 Outbox 在本地 Compose 中完成真实链路验收。阻断性并发发布缺陷已修复并复测通过。生产级身份认证、性能规模和 Redis 真实断电场景仍未纳入本轮，不能据此宣称生产就绪。

## 能力状态矩阵

| 能力 | 实现状态 | 真实证据 |
|---|---|---|
| 文件上传、尺寸校验、资产登记 | 已实现 | Playwright P0-I；数据库和 MinIO 读取校验 |
| PDF/HTML 异步处理 | 已实现 | Worker 真实执行；DocumentVersion、Segment、解析产物可查询 |
| 损坏文件失败与诊断 | 已实现 | 损坏 PDF 任务失败、错误日志保留 |
| Run 幂等、Outbox 重投与陈旧锁恢复 | 已实现 | P0-I E2E、Outbox 单元测试、Worker 恢复脚本 |
| 质量审核和恢复门控 | 已实现 | 驳回不可恢复；审核通过后显式恢复并重新执行 |
| SFT 候选、用途授权和审核分工 | 已实现 | P0-C～F 回归及真实 Web E2E |
| JSONL/Manifest 物化 | 已实现 | MinIO 实际字节、样本数、SHA-256 和签名下载校验 |
| 并发不可变发布 | 已实现 | 并发请求返回 `[200, 200]` 或 `[200, 409]`，数据库仅一个版本；Manifest ID 与数据库一致 |
| 版本和工作空间隔离 | 已实现 | 跨 workspace 查询/下载拒绝，后端权限独立执行 |
| 审计、血缘和关联日志 | 已实现 | request_id/trace_id、run/build/dataset_version 字段和反向血缘查询 |
| 正式 OIDC/SSO | 未完成 | 当前仅开发身份机制；生产环境配置会拒绝启动 |
| 大规模性能和多节点 HA | 未完成 | 本轮未执行 |

## 实际修改

### API 与领域可靠性

- `business.py`：上传文件名和声明大小校验；重复上传/完成幂等；批次 `Idempotency-Key` + 请求哈希冲突检测；分页参数与输入 DTO 约束；管理员运维统计；数据集版本发布使用 PostgreSQL 事务级 advisory lock，锁后重新读取已发布版本。
- `outbox.py`、`dispatch_outbox.py`：`FOR UPDATE SKIP LOCKED`、陈旧 `processing` 回收、按事件类型路由 pipeline 和 dataset delivery。
- `tasks.py`：运行开始/结束时间、失败重试与 NodeRun attempt、发布交付任务、失败状态诊断。
- `dataset_materializer.py`：staging 与最终不可变对象分离；异常只清理本次 staging 对象；并发发布由事务锁串行化，避免后到请求覆盖先到 Manifest。
- `main.py`、`core/logging.py`：统一错误码、`X-Request-ID`/`X-Trace-ID` 传播，结构化业务关联字段。

### 数据库与契约

- `0006_system_hardening`：`processing_batches.request_hash` 与 workspace 级幂等唯一索引。
- `0007_execution_timing`：`pipeline_runs.started_at`、`finished_at`，供运行时统计使用。
- OpenAPI 已重新导出；迁移当前 head 为 `0007_execution_timing`。

### 测试与验收材料

- 新增 `apps/web/tests/p0-i.spec.ts`、`tests/unit/test_input_hardening.py`、Outbox 并发/陈旧锁测试。
- 新增 `scripts/verify_publish_concurrency.py`，并更新数据集物化、失败路径和 Worker 恢复验证脚本。
- 计划见 [P0-I_SYSTEM_ACCEPTANCE_PLAN.md](../plans/P0-I_SYSTEM_ACCEPTANCE_PLAN.md)，真实命令输出见 [P0-I_SYSTEM_E2E.log](P0-I_SYSTEM_E2E.log)。

## 测试结果

| 类别 | 命令 | 结果 |
|---|---|---|
| Python unit/integration/contract | `uv run --locked pytest -q`（本地 Compose 变量） | **26 passed**, 16 warnings |
| OpenAPI contract | `uv run --locked pytest -q tests/contract/test_openapi.py` | **1 passed** |
| Ruff | `uv run --locked ruff check apps/api/src tests scripts` | **PASS** |
| Mypy | `uv run --locked mypy apps/api/src` | **PASS，27 source files** |
| Web typecheck/lint/build | `npm run typecheck && npm run lint && npm run build` | **PASS** |
| Playwright 真实 Docker E2E | `npm run e2e` | **3 passed** |
| P0-C～F 业务回归 | `scripts/verify_business_loop.py` | **P0-C/P0-D/P0-E/P0-F PASS** |
| 并发发布 | `scripts/verify_publish_concurrency.py` | **PASS，visible_versions=1** |
| 物化、下载、哈希和跨 workspace | `scripts/verify_dataset_materialization.py` | **PASS** |
| 失败门控、MinIO/DB 失败 | `scripts/verify_dataset_failure_paths.py` | **PASS** |
| Worker 强制终止后恢复 | `scripts/verify_worker_recovery.py` | **PASS，3/3 succeeded** |
| Docker readiness | `GET /ready` | **200；PostgreSQL、Redis、MinIO 健康** |
| Alembic | `alembic current` | **0007_execution_timing (head)** |

## 正常和异常路径证据

正常链路已由真实 Web E2E 覆盖：上传真实 PDF、异步 Run、解析内容、候选审核、JSONL 发布、Manifest、签名下载和样本反向血缘。HTTP 202 只显示排队/处理中，页面等待后端状态，不将入队视为成功。

异常链路包括：损坏 PDF 失败、上传尺寸不符、重复完成幂等、同一批次 key 的请求哈希冲突、审核驳回恢复阻断、未审核/未授权样本阻断、自审自发阻断、MinIO 写入失败、数据库提交失败以及 Worker 重启恢复。

并发发布初次复验发现对象写入竞态，导致后到请求可能覆盖先到 Manifest。已加入事务级 advisory lock，并重新构建 API、重跑并发脚本；复验得到两个请求 `[200, 200]`（第二次幂等）和单一可见版本，Manifest 与数据库版本 ID 一致。

## 安全与质量检查

- 所有关键资源查询继续带 workspace 条件；下载先执行用途授权，再生成短期签名 URL。
- 队列消息只传 run/version 业务 ID；日志不记录密码、Token 或文件正文。
- 上传文件名禁止路径分隔符、控制字符和空名称；实际字节数必须等于声明大小。
- `Idempotency-Key` 采用 workspace 作用域，重复 payload 幂等，改变 payload 返回 `IDEMPOTENCY_KEY_REUSED`。
- API 未启用宽松 CORS；部署入口需配置明确 allowlist。
- 当前开发身份认证不满足生产 OIDC/SSO；`production` 配置会阻止开发身份启动。

## 未完成事项与风险

| 风险 | 等级 | 说明 |
|---|---|---|
| 正式身份认证 | P0 出口前置 | NOT RUN；需在 P1 接入 OIDC/SSO、密钥轮换和生产会话策略 |
| Redis 真实中断注入 | P1 | 本轮未对共享本地队列执行断电；Outbox 异常重投有单元覆盖 |
| 大规模性能、多节点故障 | P1 | 未执行；当前证据只覆盖本地小规模隔离环境 |
| 上传内存占用 | P1 | 当前上传路径会将请求体读入内存，后续需流式上传和大小上限 |
| CORS/边缘安全策略 | P1 | API 不默认放宽跨域，需由部署层提供生产 allowlist、TLS 和限流 |
| MinIO 签名 URL 网络地址 | P1 | 本地签名 URL 可能使用 Compose 内部服务名，部署时需配置外部可达 endpoint |
| 测试桶历史孤儿对象 | P2 | 仅本地验收桶；生产清理需按 staging 生命周期和审计策略执行 |

## P0 追踪与覆盖

P0-A～F 的 FR/BR/AC/TC 映射仍在现有 `docs/plans/TRACEABILITY_MATRIX.md`；本轮新增的 I-01～I-14 用例已在 [P0-I_SYSTEM_ACCEPTANCE_PLAN.md](../plans/P0-I_SYSTEM_ACCEPTANCE_PLAN.md) 列出，真实结果记录在 E2E 日志。未覆盖项主要是正式 OIDC、性能/HA 和真实 Redis 断电，均明确标记为 NOT RUN，没有改写为通过。

## 本地复现

```bash
cd /Users/leon/Desktop/data
cp .env.example .env  # 填入本地占位配置
docker compose --env-file .env -f infra/compose.yaml up -d
docker compose --env-file .env -f infra/compose.yaml run --rm init
cd apps/web && npm ci && npm run e2e
cd ../..
uv run --locked ruff check apps/api/src tests scripts
uv run --locked mypy apps/api/src
uv run --locked pytest -q
```

## 进入 P1 的前置条件

1. 接入并验证 OIDC/SSO、生产密钥托管、会话撤销和最小权限映射。
2. 将上传改为流式对象写入，补齐大小/类型/压缩炸弹和病毒扫描策略。
3. 建立 Redis、MinIO、PostgreSQL 故障注入和多 Worker 压力基准。
4. 完善 staging 孤儿清理、指标导出和告警，验证外部签名 URL endpoint。
5. 在真实部署拓扑下重跑 Playwright、迁移回滚和灾备演练。

本轮到此停止，不自动进入 P1。
