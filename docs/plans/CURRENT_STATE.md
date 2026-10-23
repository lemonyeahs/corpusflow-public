# 当前状态（2026-10-23）

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
| 持久层 | 无 | SQLAlchemy 会话与 Alembic 版本基线；业务表 TODO |
| 配置/日志/错误 | 无 | Pydantic v2、JSON 请求日志、关联 ID、稳定错误 DTO |
| PostgreSQL / Redis / MinIO | 未部署 | Compose 定义与真实验证结果见验收报告 |
| IAM / 用途许可 / 业务审计 | 仅演示 | TODO P0-B，无占位业务接口 |
| Worker / 文件 / 质检 / 发布 / 血缘 | 仅演示 | TODO P0-C～F |
| 测试 | CHANGELOG 声称 14/14 | 历史脚本和 JSON 缺失，不能复现原有完整 14 项；新骨架测试独立计数 |

## 兼容策略与环境

无真实后端可复用，因此按指定栈建立 `apps/api`，统一根目录 pyproject/uv.lock 管理 Python 3.12 依赖。保留 V2/V3/V3.1 及所有用户文档，不修改旧 JS，不把演示种子导入数据库。没有重写十页前端。

Python 3.12.13（uv 管理）可用；系统默认 Python 为 3.13.7，工程不使用该版本。Docker 客户端 29.3.1、Compose v5.1.1；初始 daemon 未启动，已启动本地 Docker Desktop。依赖及迁移实际运行结果以报告为准。
