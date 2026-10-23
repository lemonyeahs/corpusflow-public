# ADR-006：P0-A 工程边界与契约

日期：2026-10-23。状态：本轮实施采用，待项目评审。

沿用技术方案 ADR-001～005 的模块化单体、独立 Worker、PG 真值与发布协议。本次仅工程骨架，业务表、权限、Outbox、Adapter 处理任务按 P0-B～F 顺序实施。根目录统一 uv.lock（Python 3.12），不复制第二套 API 项目。

OpenAPI 采用 FastAPI 导出为 `docs/api/openapi.json`；契约测试逐字结构比较，接口变更必须同步快照。根路径 `/health`、`/ready` 遵循本次用户明确要求。统一错误为嵌套 `error` + `request_id`；新增运维错误 `DEPENDENCY_UNAVAILABLE`（503）与启动诊断 `CONFIG_INVALID`。

就绪检查执行真实只读调用：PG SELECT + Alembic revision、Redis PING、S3 HeadBucket。三项并发、连接与读超时受控，失败不泄露连接串，不回退到 Mock。建桶和迁移是独立初始化步骤，探活不修改状态。HeadBucket 不代表对象写权限、内容校验或完整存储能力已验收。

P0-A 无业务鉴权，拒绝 staging/production，Compose 端口仅回环；本地开发凭证以随机值写 `.env`（0600，不入版本管理）。请求日志只写允许字段，不记录 URL query/body/header/上游异常文本。结构化日志不等于不可篡改业务审计，后者 P0-B 起实现。

迁移 0001_p0a 为无业务表基线，仅 Alembic 自建版本表；回滚不删业务数据。迁移 smoke 在新建的随机临时 PostgreSQL 库执行，要求显式回环测试管理连接。没有触碰生产迁移。

实测补充：注册表拉取失败后，采用已有 PostgreSQL 16.14 与 MinIO 2025-04-22 内容摘要；Redis 固定 7.4.8。CI 使用 ubuntu-24.04-arm 与本机实测架构一致；x86 与生产镜像安全评估未验收。完整本地 Compose 与迁移已通过。
