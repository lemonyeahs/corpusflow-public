# 当前状态（2026-10-23）

## P0-B～P0-F 最新状态（2026-10-24）

按 P0-B→P0-C→P0-D→P0-E→P0-F 顺序完成最小真实业务闭环。`0002_business、0003_immutable_release` 迁移已在真实 PostgreSQL 升级、检查、降级、再升级通过；业务脚本验证默认拒绝/用途隔离、三文件部分失败、N=3 独立 Run、审核阻断与显式恢复、SFT 候选审核/不可变发布、workspace-scoped lineage 与审计。

独立报告：[P0-B](../reports/P0-B_ACCEPTANCE_FINAL.md)、[P0-C](../reports/P0-C_ACCEPTANCE.md)、[P0-D](../reports/P0-D_ACCEPTANCE.md)、[P0-E](../reports/P0-E_ACCEPTANCE.md)、[P0-F](../reports/P0-F_ACCEPTANCE.md)。可重复入口为 `scripts/verify_business_loop.py`。

当前实现仍是受控最小闭环：开发身份 session、内置 parser、数据库字节暂存和同步 API；OIDC、Celery/Outbox、病毒扫描、外部 parser/generation、S3 发布物化、正式 Web UI/E2E 和 P1 能力保持明确未完成。没有 push 或生产迁移，V3.1 原型未覆盖。

## 本轮复验状态

磁盘释放后可用约 96 GiB。Docker 仍有残留 backend，正常退出无效；经用户明确授权终止该进程并正常启动后，旧 CorpusFlow 服务恢复健康。随后以新 builder、新测试项目和新卷完成无缓存构建、启动、真实迁移、S3 和故障恢复检查，完整本地复验通过，结束时可用约 90 GiB。

最新结果：12 项基础测试通过，4 项真实迁移/S3 测试通过，MinIO 重启后 3 项 S3 复验通过；`/ready` 200→503→200、`/health` 始终 200。本地环境阻塞 `BLK-P0B-001`、`BLK-ENV-002` 已关闭，远程 CI 未重跑。详见 [最新报告](../reports/ENV_REVERIFY_RECOVERED_ACCEPTANCE.md)。

当前 `main` 提交仍为 `b1dcb309c7edb1df930a3bc83f5b7be87dba5e75`。工作区保留环境修复、复验脚本、测试和报告的本地未提交修改。以下「审查基线」保留首次 P0-A 实施前的历史，不代表目前仍未初始化 Git。

没有新增业务代码、API 或迁移；没有推送远端、改变生产环境或删除现有数据。V3.1 原型及副本哈希一致。

## 审查基线

工作目录 `/Users/leon/Desktop/data`。`git status --short` 返回 fatal: not a git repository；未初始化 Git、未创建提交。初始无 README、pyproject、迁移、后端、配置或测试实现。上一轮中断仅留下空 `app/static`、`tests` 与 `docs/specs/需求分析.md`；空目录保留，不作为另一套工程。

新提供的技术方案为 CF-ARCH-001 v1.0，状态为建议基线、待架构评审；需求 CF-REQ-001 v1.0 尚待业务评审。根目录需求与已有 `docs/specs/需求分析.md` SHA-256 相同。新增规范名称副本，不覆盖原件。权威路径：

1. `docs/specs/CorpusFlow_01_需求分析与确认_V1.0.md`
2. `docs/specs/CorpusFlow_02_技术方案设计_V1.0.md`
3. `docs/prototype/CorpusFlow_V3_1.html`
4. `docs/prototype/CorpusFlow_V3_1_CHANGELOG.md`

## 实现分界

| 内容 | 审查前 | P0-A 交付 |
|---|---|---|
| 十页 UI、上传、审核、构建、发布、角色、RAG | HTML 内存 DEMO | 原件保留，不接业务 API |
| API / 健康检查 | 无 | FastAPI `/health`、`/ready`，真实探测 PG/Redis/S3 |
| 持久层 | 无 | SQLAlchemy 会话与 Alembic `0001_p0a`/`0002_business、0003_immutable_release`；P0-B～F 业务表已落地 |
| 配置/日志/错误 | 无 | Pydantic v2、JSON 请求日志、关联 ID、稳定错误 DTO |
| PostgreSQL / Redis / MinIO | 未部署 | Compose 定义与真实验证结果见验收报告 |
| IAM / 用途许可 / 业务审计 | 仅演示 | P0-B 最小后端策略、空间隔离、审计已实现 |
| 文件 / 质检 / 发布 / 血缘 | 仅演示 | P0-C～F 最小闭环已实现；外部适配与正式 Worker/UI 仍 TODO |
| 测试 | CHANGELOG 声称 14/14 | 历史脚本和 JSON 缺失，不能复现原有完整 14 项；新骨架测试独立计数 |

## 兼容策略与环境

无真实后端可复用，因此按指定栈建立 `apps/api`，统一根目录 pyproject/uv.lock 管理 Python 3.12 依赖。保留 V2/V3/V3.1 及所有用户文档，不修改旧 JS，不把演示种子导入数据库。没有重写十页前端。

Python 3.12.13（uv 管理）可用；系统默认 Python 为 3.13.7，工程不使用该版本。Docker 客户端 29.3.1、Compose v5.1.1；初始 daemon 未启动，已启动本地 Docker Desktop。依赖及迁移实际运行结果以报告为准。
