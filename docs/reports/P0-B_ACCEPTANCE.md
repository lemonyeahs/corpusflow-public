# P0-B 验收与阻塞报告

> 历史记录：镜像和环境的本地前置阻塞已在 [恢复后复验](ENV_REVERIFY_RECOVERED_ACCEPTANCE.md) 中关闭。本文件保留首次停止记录；P0-B 后续真实实现与通过证据见 [P0-B_ACCEPTANCE_FINAL.md](P0-B_ACCEPTANCE_FINAL.md)。

日期：2026-10-23（Asia/Shanghai）。任务：TASK-CF-002。代码基线：`b1dcb309c7edb1df930a3bc83f5b7be87dba5e75`。

**结论：BLOCKED，停止于 P0-B 前置复验。P0-B 未实施、未通过，P0-C～P0-F 未开始。** 本文是本次尝试的独立阻塞报告，不是 IAM/Policy 验收通过证明。

## BLK-P0B-001：完整依赖环境不可重建

严重程度：阻断阶段推进。技术方案第 9.1 节规定 P0-A 通过标准为「最小 API + PG/Redis/S3 可启动；CI 通过」，P0-B 前置为 P0-A。用户本轮要求严重验收失败立即停止。

首次远程 CI 在 `make up` 拉取 MinIO 时失败，详见 [上传记录](GITHUB_UPLOAD.md)。本轮没有访问或修改远程仓库，直接使用 Docker 注册表只读检查查询本地 Compose 固定的镜像摘要，结果退出码 1：

```text
ERROR: unexpected status from HEAD request to https://quay.io/v2/minio/minio/manifests/sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e: 401 Unauthorized
```

这证明当前凭证/网络条件下该镜像引用不可获取。401 的上游根因尚未确定，不能据此断言镜像删除或许可证变化。现有缓存容器的成功探活不能证明全新环境可构建，也不能消除已发生的远程 CI 失败。因此不继续扩大业务实现。

## 已执行的真实检查

| 检查 | 结果 | 原始证据 |
|---|---|---|
| ruff check / format | All checks passed；24 files already formatted | [基础检查日志](P0-B_PREFLIGHT_CHECKS.log) |
| mypy | Success: no issues found in 15 source files | 同上 |
| pytest 基础单元/契约 | 12 passed, 1 deselected, 1 warning in 1.44s | 同上 |
| PostgreSQL 迁移 smoke | 1 passed, 12 deselected, 1 warning in 0.72s | [迁移日志](P0-B_PREFLIGHT_MIGRATION.log) |
| 固定 MinIO 摘要注册表查询 | FAIL，401 Unauthorized，退出码 1 | [注册表日志](P0-B_PREFLIGHT_REGISTRY.log) |
| 当前缓存容器 HTTP | `/health` 200；`/ready` 200；phase=P0-A | [运行及原件证据](P0-B_PREFLIGHT_RUNTIME.json) |
| V3.1 HTML 与 CHANGELOG | 原件、留存副本相同；原件基线哈希断言通过 | 运行及原件证据、基础测试 |

迁移测试在本机回环 PostgreSQL 创建随机 `cf_smoke_*` 临时库，执行 upgrade → 模型差异 check → downgrade → re-upgrade，最后仅删除该测试创建的临时库。没有回退开发库、删除业务卷或访问生产数据库。该结果仅覆盖 `0001_p0a`，不是 P0-B 迁移验收。

警告是 FastAPI TestClient 对 httpx 的弃用提示，未造成测试失败。既有基础测试包含显式测试替身；表中的 HTTP 和迁移检查使用真实服务，未将替身结果算成真实服务证据。

## 可复验命令

在项目根目录执行，迁移检查仅针对已有本机开发环境：

```sh
make check
set -a
. ./.env
set +a
export CF_TEST_ADMIN_DATABASE_URL="$DATABASE_URL"
make integration
docker buildx imagetools inspect quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z@sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e
curl --fail http://127.0.0.1:58000/health
curl --fail http://127.0.0.1:58000/ready
```

不要打印 `.env` 或数据库 URL。不要删缓存、删卷或停止现有服务来复现镜像故障；注册表查询已经绕开本地镜像缓存。

## 对应需求及未执行范围

- P0-B 目标：FR-010/027/028/041、BR-AUTH-*、BR-GOV-02/04、AC-IAM-*、TC-05/06/07/08/19。全部业务实现与测试仍 TODO。
- 前置复验：NFR-01/06/08、TC-25/26/28 的基础工程切面。不能据此宣布完整需求通过。
- P0-B 没有新增身份、授权、审计表或 API；OpenAPI 和迁移头不变。
- P0-C～P0-F 没有实现、迁移或业务测试结果，不生成虚假阶段报告。完整当前映射见 [需求追踪矩阵](../plans/TRACEABILITY_MATRIX.md)。

## 实际修改文件

- `docs/plans/IMPLEMENTATION_PLAN.md`：记录本轮授权、严格门禁与阶段状态。
- `docs/plans/CURRENT_STATE.md`：区分历史审查基线与本轮实测状态。
- `docs/plans/OPEN_DECISIONS.md`：更新 OD-13/17，登记本轮阻塞。
- `docs/plans/TRACEABILITY_MATRIX.md`：增加本轮最终状态，业务映射保留 TODO。
- `docs/reports/P0-B_ACCEPTANCE.md`：本报告。
- `docs/reports/P0-B_PREFLIGHT_CHECKS.log`、`P0-B_PREFLIGHT_MIGRATION.log`、`P0-B_PREFLIGHT_REGISTRY.log`、`P0-B_PREFLIGHT_RUNTIME.json`：本轮真实证据。

本轮没有新增业务源代码或测试，没有创建 Git 提交或 push，没有修改生产环境、原型、规范原件、现有凭证或容器配置。既有服务继续运行。

## 解除阻塞的条件

1. 确认可合法获取的 MinIO 镜像来源及内容摘要，或由环境负责人通过安全凭证渠道提供必要的只读注册表访问。不把凭证写入报告或 Git，也不要求提供生产密钥。
2. 在独立开发/测试环境验证新环境可拉取依赖，并重放 CI 全部步骤：锁定安装、基础检查、Compose 构建启动、真实数据库迁移、真实 S3/Redis/PG readiness。保留现有数据与缓存。
3. 记录修复证据及门禁结论后，重新启动 P0-B；P0-B 自身真实测试、迁移及独立报告通过后才能进入 P0-C。

本轮禁止 push，所以未通过推送触发远程 CI。后续可以先本地隔离环境重放；如需远程重验，必须遵守届时的远端操作授权。本轮未自行切换对象存储、寻找未知第三方镜像或降低阶段通过标准。
