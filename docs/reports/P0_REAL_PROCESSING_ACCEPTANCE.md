# P0 真实异步处理与 PDF/HTML 解析验收

日期：2026-10-24  
前置审查：[P0_CLOSURE_AUDIT.md](P0_CLOSURE_AUDIT.md)

## 实际交付

- 新增 `0004_async_processing` 迁移：`outbox_events`、`execution_logs`；当前本地数据库已升级至该 revision。
- `PipelineRun` 批量创建和显式 execute/resume 只写 PostgreSQL 状态与 Outbox，API 返回 202，不执行正文处理。
- 新增 Redis/Celery Worker、Outbox Dispatcher Docker 服务。消息只含 `run_id`；Worker 以 PostgreSQL 行锁声明执行权，成功状态和产物由 PostgreSQL 决定。
- Worker 从 MinIO/S3 读取 `AssetBlob.storage_key` 的真实字节，写入 Markdown/JSON 中间产物，并创建 `DocumentVersion`、`Segment`、执行日志和 Asset→PipelineRun→DocumentVersion→Segment 血缘。
- 新增独立 `HTMLParserAdapter` 和 `PDFParserAdapter`。HTML 使用标准库解析可见文本和标题定位；PDF 使用 pypdf 提取页文本。加密、损坏、扫描/无文本 PDF 分别返回稳定错误码，不伪造结果。
- `GET /api/v1/pipeline-runs/{run_id}/logs` 提供执行日志；rejected/isolated 仍拒绝恢复，审核通过后须显式 resume 重新入队。
- Docker Compose 新增 `worker` 和 `dispatcher`，本地环境启动后由 Dispatcher 重投 pending Outbox。

## 数据库和 API 变化

迁移链：`0001_p0a → 0002_business → 0003_immutable_release → 0004_async_processing`。新增表：`outbox_events`、`execution_logs`。新增 API：执行入口的异步 202 语义、`GET /pipeline-runs/{run_id}/logs`；OpenAPI 已重新导出。

## 验收命令与结果

| 检查 | 命令/证据 | 结果 |
|---|---|---|
| 迁移 | `docker compose ... run --rm init`；`select version_num from alembic_version` | PASS，`0004_async_processing` |
| 依赖锁定 | `uv lock` / 镜像 `uv sync --locked --no-dev` | PASS，包含 `pypdf==5.9.0` |
| 静态检查 | `uv run --locked ruff check apps/api/src tests` | PASS |
| 类型检查 | `uv run --locked mypy` | PASS，25 source files |
| 单元/契约测试 | `uv run --locked pytest -q` | PASS，16 passed，4 skipped（1 个 Starlette warning） |
| 解析器与 Outbox | `tests/unit/test_real_processing.py`、`tests/unit/test_outbox.py` | PASS，4 passed；覆盖 HTML、损坏/扫描 PDF、Outbox 重投和幂等 |
| 完整容器启动 | `docker compose ... build api worker dispatcher init && up -d` | PASS，API/Worker/Dispatcher/PostgreSQL/Redis/MinIO healthy/running |
| 真实 HTML/PDF/损坏 PDF | `uv run --locked python scripts/verify_real_processing.py` | PASS；HTML succeeded、PDF succeeded、损坏 PDF failed `CORRUPT_PDF` |
| 真实对象与产物 | `docs/reports/P0_REAL_PROCESSING_SMOKE.log`；PostgreSQL 查询 | PASS；HTML/PDF 各 2 个不可变 Artifact、执行日志和 4 条血缘边（含 run 链） |
| 重复投递 | Celery 重投同一成功 run；数据库查询 | PASS；Artifact 仍为 2、ExecutionLog 仍为 1，无重复产物 |
| Redis 短暂不可用 | `tests/unit/test_outbox.py` Dispatcher failure 分支 | PASS（可恢复 pending/attempts）；未在生产 Redis 上断电 |
| 跨 workspace、审核拒绝/批准恢复 | P0-F 业务测试与现有报告 | PASS（门控）；本阶段未把 Mock 结果当解析证据 |
| Worker 运行中终止 | 未执行破坏性容器终止 | NOT RUN；需在专用恢复测试环境执行 |

真实 smoke 输出摘要：

```text
ingest ... total=3 succeeded=3
HTML run: succeeded, parsed builtin.html sections=1 bytes=35
PDF run: succeeded, parsed builtin.pdf sections=1 bytes=628
bad PDF run: failed, parser failure CORRUPT_PDF
```

## 已知限制与风险

- Dispatcher 是本地 Compose 进程；生产部署仍需进程监管、指标、死信策略和锁超时回收。Outbox `published` 只表示消息已交给 Redis，不表示业务成功。
- Worker 通用异常当前记录 `PROCESSING_ERROR`；下一阶段应细化可重试错误、退避、最大重试和僵尸 `running` 恢复策略。
- PDF 解析器是轻量本地实现，不覆盖复杂布局、OCR、表格和脚注；扫描版/加密/损坏输入明确失败。
- UploadSession 仍保留兼容性 `content` 列，后续应移除正文入库路径并补齐分片校验、病毒扫描和对象生命周期策略。
- 当前端到端验证使用本地 Docker 数据库，已保留既有验收和本次合成测试记录；没有生产数据库、密钥或远程 push。

## 下一阶段依赖

数据集对象物化和前端联调需要：稳定的 Artifact manifest/schema、对象下载授权与签名 URL、DatasetVersion 物化任务、质量规则和审核 UI、血缘查询分页、Worker/Outbox 指标及专用故障恢复环境。
