# P0-A 验收记录

日期：2026-10-23（Asia/Shanghai）。任务：TASK-CF-001。结论：**本地工程骨架验收通过；不是业务系统或生产就绪验收。** 已停止进入 P0-B。

## 范围及追踪

以 CF-REQ-001 MUST/BR/AC 为业务基线、CF-ARCH-001 第 9/10 节为阶段和任务依据；V3.1 仅作 UI/流程参考。对应 NFR-01（配置/日志安全基础）、NFR-06（请求关联）、NFR-08（基础检查）、TC-25（错误/契约）、TC-26（迁移）、TC-28（仅请求日志脱敏）。

FR-010/041 的身份和审计仅预留边界，**未完成**。AC-IAM、AC-ING、AC-RUN、AC-QA、AC-BUILD、AC-LINEAGE 均 TODO；不将基础检查套用为这些业务验收通过。详见 `docs/plans/TRACEABILITY_MATRIX.md`。

## 实际变更

- `apps/api/src/corpusflow/main.py`：FastAPI factory、生命周期、关联 ID、统一异常响应。
- `core/config.py`、`errors.py`、`logging.py`：必需配置/脱敏启动诊断、Pydantic DTO、JSON 日志。
- `api/health.py`、`adapters/readiness.py`：存活与真实依赖就绪；三依赖并发探测、有限超时、失败 503。
- `db/session.py`、`alembic.ini`、`apps/api/alembic/*`：SQLAlchemy Session/连接池、Alembic 版本初始化。
- `modules/*/README.md`、`worker/README.md`、`apps/web/README.md`：阶段边界；无假业务 API、无任务模拟。
- `infra/compose.yaml`、`infra/docker/Dockerfile`：隔离 PG/Redis/MinIO、初始化容器和非 root API。
- `pyproject.toml`、`uv.lock`、`.python-version`、`.env.example`、`.gitignore`、`.dockerignore`：Python 3.12 与可复现依赖、占位配置。
- `scripts/init_env.py`、`init_storage.py`、`export_openapi.py`、`Makefile`、`README.md`：本地启动、显式建桶、OpenAPI 导出和检查。
- `tests/unit/test_foundation.py`、`tests/contract/test_openapi.py`、`tests/integration/test_migration.py`：基础、错误、失败探活、原件哈希、契约及真实迁移。
- `.github/workflows/ci.yml`：ARM64 runner 的锁定依赖、静态/类型/测试、完整 Compose、临时库迁移与 readiness。
- 四份计划文档、ADR-006、`docs/api/openapi.json`、规范与原型副本及本报告。

全部新增交付文件清单见 `P0-A_FILES.txt`。原先空 `app/static` 目录仍保留，不构成另一套实现。`.env` 是本地随机开发凭证（0600），不列入交付清单，不打印、不提交。

## 实测环境

macOS ARM64；uv 0.11.2；Python 3.12.13；Docker 29.3.1；Compose v5.1.1。实际 PostgreSQL 16.14、Redis 服务镜像 7.4.8、MinIO RELEASE.2025-04-22T22-12-26Z。PG 与 MinIO 按实测内容摘要固定，见 Compose。

锁文件：FastAPI 0.135.4、Pydantic 2.14.1、SQLAlchemy 2.0.55、Alembic 1.20.1、psycopg 3.3.6、redis Python client 7.4.1、Celery 5.6.3、boto3 1.43.118；pytest 9.1.1、ruff 0.15.22、mypy 1.20.2。Celery 仅锁定依赖，没有运行 Worker。

## 运行与验证命令

在根目录执行：

```sh
make init-env  # 已有 .env 时不执行；脚本拒绝覆盖
make up
make install
make check
```

访问 `http://127.0.0.1:58000/health`、`/ready`、`/docs`。本轮完整 Compose 已成功，API 保留运行以便核对，`make down` 可停止且保留卷。

迁移测试：

```sh
set -a
. ./.env
set +a
export CF_TEST_ADMIN_DATABASE_URL="$DATABASE_URL"
make integration
```

测试只在回环服务上新建 `cf_smoke_<random>` 临时数据库，执行 upgrade/check/downgrade/upgrade 后删除该临时库，未对用户已有库运行 downgrade。应用开发库 `corpusflow` 仅 upgrade 至 `0001_p0a`。

## 真实输出与证据

| 验收 | 实际结果 | 原始记录 |
|---|---|---|
| ruff check | All checks passed! | `P0-A_CHECKS.log` |
| ruff format --check | 24 files already formatted | 同上 |
| mypy strict | Success: no issues found in 15 source files | 同上 |
| 单元/契约 | 12 passed, 1 deselected, 1 warning | 同上 |
| PostgreSQL 升降级/重升/模型差异 | 1 passed, 12 deselected；No new upgrade operations detected. | `P0-A_MIGRATION.log` |
| 当前迁移版本 | 0001_p0a (head) | 同上 |
| 完整 Compose | PG/Redis/MinIO/API Healthy；init Exited 0 | `P0-A_COMPOSE_FINAL.log` |
| 真实 HTTP | /health 200；/ready 200；/openapi.json 200 | `P0-A_FINAL_VERIFICATION.log` |
| Redis 故障/恢复 | /ready 200 → 503 → 200；故障中 /health 仍 200 | `P0-A_HTTP.log` |
| 无配置启动 | exit 1；CONFIG_INVALID 列出缺失字段，未打印值 | `P0-A_FINAL_VERIFICATION.log` |
| 原件保留 | 四文件与副本逐字节相同；原 HTML/CHANGELOG/需求哈希断言通过 | 同上及基础测试 |

Redis 故障测试仅停止本项目容器后恢复，没有停止其他项目服务。该测试使用额外本机 API 58001；该临时进程已停止，最终交付使用容器 API 58000。

实际响应示例（关联 ID 为实测值）：

```json
{"status":"ready","phase":"P0-A","request_id":"86dbb53d9ec343b9b7ec0942dda314c4"}
```

## API / 数据迁移 / 回滚

新增 `/health`、`/ready`；OpenAPI 仅含这两个业务定义路径，没有伪造 `/api/v1/assets` 等接口。统一错误包含 `error.code/message/details/retryable` 和 `request_id`；响应头 `X-Request-ID` 与响应体一致。不合法输入 ID 被重新生成。

`0001_p0a` 不建立任何业务表，只有 Alembic 版本表/标记。此举符合 P0-A 边界，IAM 及业务约束 P0-B 起追加；不宣称数据库已具备授权或不可变发布能力。

本地回滚：`make down` 保留卷；必要时备份开发数据库，再 `uv run --locked alembic downgrade base` 回退版本标记。未提供生产自动迁移或删卷命令；V3.1 原件没有变更可回滚项。

## 失败、限制与未执行项

1. 初次 Docker Hub MinIO 拉取拒绝访问、Quay 新 tag 返回 401、PG 固定 patch tag 请求 EOF。保留 `P0-A_COMPOSE.log` 的失败证据；采用本机已有 PG16/MinIO 的内容摘要后，完整启动通过。不是用 Mock 替代服务。
2. 固定 MinIO 镜像是较早版本，仅用于本地 P0-A；正式部署前需要镜像安全/许可证评审和更新验证。当前 CI 使用 ARM64，与实测宿主一致；x86_64 镜像兼容未验收。
3. pytest 有一条上游 Starlette/httpx 迁移弃用警告；不影响本轮测试，但未来需升级测试客户端。Alembic path_separator 警告已修正。
4. 没有 Git 仓库，因此没有 commit ID、未初始化 Git、未 push；远程 GitHub Actions **未运行**。本地已执行 CI 的核心检查与 Compose/迁移步骤，不能称远程 CI 通过。
5. 旧原型声称 14/14 的 Playwright 脚本和 JSON 不存在；未复现这 14 项，也未做浏览器截图或业务 UI E2E。
6. HeadBucket 只验证桶可访问，未验收 multipart、病毒扫描、文件 SHA、对象锁/WORM；MinIO bucket versioning 不等于发布不可变策略。
7. 本阶段没有 IAM/RBAC、工作空间隔离、用途策略、不可变审计、Outbox、Worker、业务状态机、解析、LLM、数据集或血缘实现。请求日志不能替代业务审计。拒绝 staging/production 配置，非生产系统。
8. 未执行压测、依赖漏洞扫描、正式安全评估、备份恢复演练或生产迁移。

## 下一步依赖与人工确认

P0-B 依赖本次骨架，下一任务 TASK-CF-002 为 IAM + Policy，需要确认身份方案、空间成员角色、授权证据责任人/有效期以及跨空间资源策略。未确认时默认拒绝；不继承 HTML 模拟许可。业务/技术规范签署仍待负责人确认。

本轮不自动实施 P0-B。没有需要用户再次批准才能完成的 P0-A 剩余代码动作。
