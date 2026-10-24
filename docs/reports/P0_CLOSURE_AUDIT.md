# CorpusFlow P0 收尾审查

日期：2026-10-24  
基线：本地 `main`，HEAD `b1dcb309c7edb1df930a3bc83f5b7be87dba5e75`（审查开始时）

## 审查范围

已阅读 `docs/specs/CorpusFlow_01_需求分析与确认_V1.0.md`、`docs/specs/CorpusFlow_02_技术方案设计_V1.0.md`、`docs/reports/P0_BUSINESS_ACCEPTANCE.md`、P0-B～P0-F 各阶段报告、OpenAPI、Alembic 迁移、SQLAlchemy 模型、Docker Compose、V3.1 HTML 与 CHANGELOG。

## 真实能力与边界

| 能力 | 审查结论 |
|---|---|
| 身份、工作空间隔离、角色与用途授权 | 已有 API、数据库约束和审计写入；跨工作空间查询由 workspace 条件拒绝 |
| 资产上传 | 已能写入 MinIO/S3，并在 PostgreSQL 保存对象元数据；历史 `UploadSession.content` 仍是兼容字段 |
| PipelineRun/NodeRun | 已有持久化状态机和批量 N 独立 Run；此前 execute 曾同步生成固定文本，已在本阶段改为入队 |
| Outbox/Celery/Redis | 审查时缺失；本阶段新增 `outbox_events`、发布器、Celery Worker 和 Docker worker 服务 |
| PDF/HTML | 审查时缺失真实 ParserAdapter；本阶段新增分别实现的内置解析器，读取 S3 实际字节 |
| 产物与血缘 | P0-F 原来只有元数据；本阶段 Worker 写入 Markdown/JSON 对象，生成 DocumentVersion/Segment 和 Asset→Run→DocumentVersion→Segment 血缘 |
| 发布不可变性 | 0003 PostgreSQL trigger 已实现；本次不改变发布物化边界 |
| 质量审核 | `awaiting_review`、rejected/isolated 禁止恢复；approved_for_rework 需显式 resume 并重新入队 |

## 阻断缺陷与修复

1. **API 同步处理耗时任务**：`POST /pipeline-runs/{id}/execute` 直接读取数据库正文并创建产物。已改为事务写入 Outbox，返回 202；正文处理只在 Worker 执行。
2. **对象存储只写不读**：Worker 现在按 `AssetBlob.storage_key` 从 S3/MinIO 获取字节；解析结果写回对象存储。
3. **缺少失败和执行日志**：新增 `execution_logs`，记录解析器版本、输入字节、分段数量和错误码。

## 仍需关注

- Outbox 调度器目前提供可复用的 `publish_pending` 服务函数，生产环境需以独立受管进程定时调用；API 没有把 Redis 投递当作任务成功。
- 当前解析器是本地轻量实现，扫描 PDF、加密 PDF、损坏文件显式失败；未接入 WeKnora/docreader。
- 历史测试主要覆盖业务门控；审查前缺少 Worker 崩溃、重复投递、Redis 不可用的集成覆盖，本阶段新增单元/集成测试并在验收报告中逐项标记实际执行状态。
- 本地开发数据库保留既有验收脚本产生的合成记录，未删除任何数据。

## 工作区与供应链检查

审查时存在未提交的 P0-A～P0-F 代码、报告和本阶段改动；`.env` 被忽略且未纳入提交，未发现密钥字符串或大于 10 MB 的工程文件。V3.1 原型及 CHANGELOG 未被覆盖，SHA256 保持：HTML `b65d5ac9a0dd81d28dcf5297cddf0789a214bcbd9922ca88b19d1e8f0f98ea32`，CHANGELOG `10733bade01c525a523ad320960d84697896c526a6f2cbdb4d82b4f47a5f3b50`。
