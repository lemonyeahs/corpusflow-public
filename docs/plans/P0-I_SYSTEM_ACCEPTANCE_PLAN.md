# CorpusFlow P0-I 系统级验收与工程质量加固计划

日期：2026-10-24
基线：`9dcd81d`（P0-H，远程 `main` 已同步）
范围：系统级验收、故障恢复、并发安全、可观测性和质量缺陷修复；不进入 P1。

## 风险分级

| 风险 | 现状证据 | 验收目标 |
|---|---|---|
| P0 阻断 | 处理批次保存了 `idempotency_key`，但创建接口未查询或约束，重复请求可生成多组 Run | 相同 key + 相同请求返回原批次；同 key + 不同请求稳定冲突 |
| P0 阻断 | Outbox 读取未使用数据库行锁，多个 Dispatcher 可同时投递；`dataset.version.deliver` 被通用 Dispatcher 当作解析任务投递 | `FOR UPDATE SKIP LOCKED`、陈旧 processing 可恢复、事件按类型路由，重复投递不重复产物 |
| P1 高 | 上传接口未校验实际字节数与声明大小；对象 key 直接拼接用户文件名 | 超限/短包被拒绝，文件名不能穿越或污染对象路径 |
| P1 高 | Worker 通用异常记录失败后直接抛出，未创建下一次 NodeRun，Celery `max_retries` 不会自动重试 | 临时故障进入可追踪重试，永久解析错误保持失败，恢复后不重复产物 |
| P1 中 | 运行状态、Outbox 积压和发布失败缺少统一统计；请求日志缺少 asset/dataset-version 关联头 | 增加受保护运维统计和结构化关联字段，不记录密钥或正文 |
| P1 中 | 若干输入使用裸 `dict` 或无边界 query 参数 | 使用 Pydantic/Query 约束，并维持统一错误码 |

## 测试对象与环境

- 应用：FastAPI API、Vite Web、Celery Worker、Outbox Dispatcher。
- 依赖：本地 Docker Compose 的 PostgreSQL、Redis、MinIO；使用隔离 verifier bucket 和临时测试数据库，不访问生产。
- 数据：每次 E2E 使用唯一 workspace 和测试身份；PDF 使用仓库内真实夹具，损坏 PDF 使用明确无效字节。
- 证据：pytest、ruff、mypy、OpenAPI 契约、Alembic upgrade/downgrade/re-upgrade、Playwright、Docker CLI 日志、MinIO 哈希读取和 PostgreSQL 查询。

## 验收用例

| 编号 | 用例 | 预期 |
|---|---|---|
| I-01 | Web 真实 PDF 上传、对象读取、批次登记 | Asset、Blob、MinIO 对象和 SHA-256 一致 |
| I-02 | 异步解析和 Web 刷新 | API 返回 202/queued，Worker 产出 DocumentVersion、Segment、Markdown/JSON |
| I-03 | 损坏 PDF | 任务 `failed`，错误码为 `CORRUPT_PDF`，ExecutionLog 保留诊断 |
| I-04 | 质量驳回/通过恢复 | rejected/isolated 不可恢复；approved_for_rework 需显式 resume |
| I-05 | SFT 构建、审核、发布、下载、反向血缘 | 分工、用途授权、JSONL/Manifest 哈希和来源链一致 |
| I-06 | 角色和 workspace 隔离 | viewer/engineer/reviewer 的后端动作受限，跨 workspace 返回拒绝 |
| I-07 | 重复处理投递 | 同一 Run 只生成一组 DocumentVersion/Artifact/Segment |
| I-08 | 上传重复完成/尺寸错误 | 已验证上传幂等；实际大小不符稳定失败 |
| I-09 | 批次幂等与并发 | 相同 key 不生成重复 Run；不同 payload 冲突 |
| I-10 | Outbox 并发、Redis 短暂不可用、Dispatcher 重复 | 事件最终可重投，不重复业务产物，陈旧 processing 可恢复 |
| I-11 | Worker 终止后恢复 | 隔离本地 Worker 停止/重启后 Run 最终成功或保留可诊断失败 |
| I-12 | 发布并发和对象/事务失败 | 单一版本、不可覆盖；DB 失败不出现可见版本，孤儿对象有清理记录 |
| I-13 | 前端异常状态与响应式布局 | 失败/超时/空数据可见，202 不显示为业务成功，桌面/窄屏无溢出 |
| I-14 | 可观测性 | request/trace 与业务 ID 可关联，运维统计不暴露密钥和正文 |

## 修复边界

本轮允许增加 0006 质量加固迁移、输入校验、Outbox/Worker 可靠性修复、运维统计和系统级回归测试。不得改变已发布版本、删除现有数据、连接生产、接入正式 OIDC 或新增 P1 业务产品。

## 门禁

1. 先通过静态检查、契约和迁移 smoke，再启动完整 Compose。
2. 真实 API/Worker/MinIO E2E 和故障测试必须记录实际输出。
3. 任何无法安全执行的故障注入标记 `NOT RUN`，说明原因，不改写为 PASS。
4. 仅当阻断缺陷修复并复测通过，才可判定开发/演示环境 P0 退出门禁；生产认证和大规模性能仍单独列为前置条件。
