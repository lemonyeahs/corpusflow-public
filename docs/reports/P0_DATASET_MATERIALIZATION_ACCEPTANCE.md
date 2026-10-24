# CorpusFlow P0-G 真实数据集物化与发布验收

日期：2026-10-24
范围：在 P0-A～P0-F 和 P0 真实异步处理基础上，实现 SFT JSONL、Manifest、不可变发布和签名下载。没有访问生产环境，没有远程 push。

## 实际实现

- DatasetBuild 在验证时保存 validated_snapshot_hash 和 validated_by。发布重新校验构建配置哈希、候选状态、审核记录、证据、来源和用途授权；配置变更、未审核样本、自审自发都会阻断。
- 新增 services/dataset_materializer.py。它从构建快照的 CandidateSample 读取实际 messages 和 evidence_ids，校验消息格式和 Segment/DocumentVersion/Source 关系，按 source_id 做稳定 Train/Validation/Test 分组，保证同一来源不跨划分。
- 物化生成真实 JSONL，计算字节数、SHA-256、样本数、划分数和 builtin-whitespace-1 Token 统计。Manifest 包含数据集/版本/构建、配置快照、样本与来源/Segment 引用、审核用途、授权用途、统计、对象路径和哈希。
- 写入协议为 staging JSONL/Manifest → 回读并校验哈希 → 写入不可变版本对象 → PostgreSQL 事务写入版本、Artifact、DatasetVersionSample、LineageEdge 和 DatasetVersion Outbox。失败会清理已写入对象；数据库提交失败不会创建可见的已发布版本。
- 新增 DatasetVersionArtifact 表，保存不可变 JSONL/Manifest 对象元数据。0005_dataset_materialization 更新 PostgreSQL 发布版本触发器，发布版本任何字段更新都会被拒绝。
- 新增 API：GET /api/v1/datasets/{dataset_id}/versions、GET /api/v1/datasets/{dataset_id}/versions/{version}/manifest、GET /api/v1/datasets/{dataset_id}/versions/{version}/download?purpose=training。原 POST /api/v1/datasets/{dataset_id}/versions 现在执行真实物化并保持幂等。
- 下载 API 检查 workspace、版本状态和用途级授权，仅返回 300 秒签名 URL；不返回永久 MinIO 凭证或永久地址。
- 新增本地验证脚本：scripts/verify_dataset_materialization.py、scripts/verify_dataset_failure_paths.py、scripts/verify_worker_recovery.py。

## 数据库迁移

迁移链更新为：

    0001_p0a → 0002_business → 0003_immutable_release
             → 0004_async_processing → 0005_dataset_materialization

0005 新增/变更：dataset_builds.validated_snapshot_hash、validated_by；dataset_versions 的 Manifest/JSONL 对象路径、字节数、样本/划分/Token 统计、Tokenizer 版本、发布时间；dataset_version_artifacts；发布版本不可变触发器规则扩展。

真实开发库当前 Alembic revision：0005_dataset_materialization。

## 真实文件证据

P0_DATASET_MATERIALIZATION_SMOKE.log：

    DATASET_MATERIALIZATION PASS
    jsonl_bytes=734
    sha256=1f3e71e2ad9a5f08ccdbed3e8ffb0bffcf41e732928808f93cd9d9b61d8e78de
    signed_download=true
    duplicate_idempotent=true
    cross_workspace_denied=true

本次验证从 MinIO 读取 JSONL，并确认数据库 content_sha256、Manifest content.sha256 和实际文件哈希一致。样本来自已审核的现有候选样本，没有使用 Mock 生成结果冒充模型产物。

## 故障与门控证据

P0_DATASET_FAILURE_PATHS.log：

    DATASET_FAILURE_PATHS PASS
    config_changed_blocked=true
    unreviewed_blocked=true
    self_approval_blocked=true
    minio_failure_no_version=true
    db_commit_failure_no_version=true

其中 MinIO 测试停止并恢复的是本地 Compose MinIO；数据库提交失败测试使用隔离的唯一键冲突夹具，确认对象清理且无可见 DatasetVersion。已有 P0-E 回归同时覆盖了审核驳回、用途授权和不可变发布门控。
唯一键冲突现返回稳定错误码 `VERSION_CONFLICT`（HTTP 409），不会把冲突误报为已发布。

P0_WORKER_RECOVERY.log：

    WORKER_RECOVERY PASS
    run_count=3
    statuses=["succeeded", "succeeded", "succeeded"]
    worker_restarted=true

该测试在本地 Compose 中停止 Worker，保留 Redis 队列，再启动 Worker，3 个独立 Run 均恢复完成。

## 测试命令与结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 静态检查 | uv run --locked ruff check apps/api/src tests scripts | PASS |
| 类型检查 | uv run --locked mypy | PASS，27 source files |
| 全量测试（默认） | uv run --locked pytest -q | 19 passed，4 skipped |
| 全量测试（本地 PG/MinIO opt-in） | 设置 `APP_ENV`、`DATABASE_URL`、`REDIS_URL`、`OBJECT_STORE_*` 及 `CF_TEST_*` 回环变量后 `uv run --locked pytest -q` | 23 passed |
| 迁移 | CF_TEST_ADMIN_DATABASE_URL=... uv run --locked pytest -q tests/integration/test_migration.py | PASS，1 passed |
| 对象存储 | CF_TEST_OBJECT_STORE_ENDPOINT=... uv run --locked pytest -q tests/integration/test_storage.py | PASS，3 passed |
| P0-B～F 回归 | uv run --locked python scripts/verify_business_loop.py | PASS：P0-C、P0-D、P0-E、P0-F |
| 数据集发布 E2E | uv run --locked python scripts/verify_dataset_materialization.py | PASS |
| 失败与回滚路径 | uv run --locked python scripts/verify_dataset_failure_paths.py | PASS |
| Worker 停止恢复 | uv run --locked python scripts/verify_worker_recovery.py | PASS |
| Compose 环境 | docker compose ... ps | API/Worker/Dispatcher/PostgreSQL/Redis/MinIO 正常运行 |

上一阶段默认的四个 skipped 测试逐项说明：

1. tests/integration/test_migration.py：默认未设置 CF_TEST_ADMIN_DATABASE_URL，避免误连任意数据库；本轮已用回环 PostgreSQL 临时数据库 opt-in 执行并通过。
2. tests/integration/test_storage.py::test_real_multipart_hash_and_versioning：默认未设置 CF_TEST_OBJECT_STORE_ENDPOINT；本轮创建 cf-verify-* 本地 MinIO 桶并通过。
3. tests/integration/test_storage.py::test_real_invalid_credentials_denied：同上，已在本地隔离桶执行并通过。
4. tests/integration/test_storage.py::test_real_restart_persistence：同上，已在本地隔离桶执行并通过；默认套件仍保持跳过以防误用开发桶。

## 已知限制

- 发布 API 当前在请求内完成物化；超大数据集应在后续拆为 DatasetMaterialization Celery 任务，并继续使用 Outbox 状态机。
- 分词统计使用确定性的 builtin-whitespace-1，未使用正式模型 tokenizer；当前没有真实 LLM 生成步骤。
- 版本对象采用稳定路径和数据库唯一约束，MinIO 版本控制仍可能保留删除标记/历史版本；需要后续对象生命周期与孤儿 staging 清理任务。
- Presigned URL 的 endpoint 在本地 Compose 为 minio:9000，容器内可用；前端联调需要配置外部可访问的签名 endpoint。
- 生产还需要 OIDC、下载审计指标、限流、死信和大文件分片物化策略。

## 回滚与下一步依赖

回滚前先停止 API/Worker，保留并备份数据库和对象桶；不要删除已发布版本对象。代码回滚需先恢复应用兼容旧字段，再按迁移顺序在本地测试库验证 0005 downgrade；生产不执行自动回滚。

下一阶段依赖包括 DatasetVersion 前端展示、签名 URL 下载组件、Manifest schema 客户端、数据集对象生命周期、分页血缘查询和发布任务指标。P0-G 完成后停止，不自动进入 P0-H。
