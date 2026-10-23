# CorpusFlow｜交给 Codex 的开发执行提示词

> 使用前请把四份现有文件复制到同一个 Git 项目，保持原始文件不被覆盖。建议规范路径：
>
> - `docs/specs/CorpusFlow_01_需求分析与确认_V1.0.md`
> - `docs/specs/CorpusFlow_02_技术方案设计_V1.0.md`
> - `docs/prototype/CorpusFlow_V3_1.html`
> - `docs/prototype/CorpusFlow_V3_1_CHANGELOG.md`
>
> 如果暂时没有按上述路径重命名，也可以把原文件直接放在仓库根目录；以下提示词要求 Codex 先自动定位四个文件并建立对应关系。建议先运行下面的 **首次启动提示词**，检查结果后再用 **继续开发提示词** 推进后续阶段。

---

## 提示词一：首次启动（仓库审计 + P0-A 工程骨架）

你现在担任 CorpusFlow 项目的资深技术负责人兼实施工程师。目标是将现有 V3.1 **纯浏览器模拟原型**逐步开发为具有真实文件接入、持久化任务、质检审核、数据集构建、不可变发布和血缘追踪能力的工程系统。

### 1. 输入文件与读取要求

在**当前项目根目录**定位并完整阅读以下四份材料（可接受文件名带《》、`(1)` 等上传后缀；优先使用 `docs/specs`、`docs/prototype` 中的规范命名）：

1. 《CorpusFlow 需求分析与确认》：需求、角色、业务规则、验收和优先级的主要依据。
2. 《CorpusFlow 技术方案设计》：模块、数据库、API、接口适配、工程规范及 P0-A～P0-F 顺序的设计依据。
3. `CorpusFlow_V3_1.html`：十个页面和现有交互逻辑的**UI/流程参考**，不代表真实后端已实现。
4. `CorpusFlow_V3_1_CHANGELOG.md`：既有缺陷、修复结果、能力边界和原型测试的回归参考。

不要依赖文件名猜测内容。若存在冲突：以已确认的需求文档 MUST / BR / AC 为业务基线，以技术方案为默认架构，以 V3.1 HTML 为表现参考，CHANGELOG 为历史说明；将冲突记录到 `docs/plans/OPEN_DECISIONS.md`。凡许可证、数据用途或权限不确定时采取 **默认拒绝**，不得自行放宽门控。对不阻塞当前阶段的问题作保守假设、记录原因并继续；对会导致安全/数据丢失的歧义明确报阻塞。

### 2. 先审查已有仓库

执行 `pwd`、目录扫描、`git status`、依赖检查、现有 README/配置/代码/测试检查；判断这是空仓库、单页原型还是已有后端。保留用户既有修改，不覆盖或删除 V3.1 和需求文档。若已有工程栈，先列差异和兼容计划，不要未经分析就另建重复项目。

请输出/更新：

- `docs/plans/CURRENT_STATE.md`：哪些是真实现、哪些只是 DEMO、已有测试是否可复现。
- `docs/plans/IMPLEMENTATION_PLAN.md`：按技术文档 **P0-A → P0-B → P0-C → P0-D → P0-E → P0-F** 拆分任务、依赖、模块、文件改动、数据库/API、可验收结果。
- `docs/plans/TRACEABILITY_MATRIX.md`：FR/BR/AC/NFR/TC → 模块/API/表/测试映射；尚未实现标 TODO。
- `docs/plans/OPEN_DECISIONS.md`：需业务确认但不会默认放宽的决策及暂行行为。

每个任务使用技术方案第 10 节的 `TASK-CF-XXX` 模板，标出 P0/P1 及不在范围。**P0 不包含把所有外部组件一次性接好**。

### 3. 工程与架构约束

若现有仓库无可复用真实后端，默认采用：Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2.x、Alembic、PostgreSQL 16+、Redis/Celery、MinIO/S3 对象存储、pytest/ruff、Docker Compose。选择模块化单体 API + 独立 Worker，不在 P0 拆成微服务。

分层遵守 `API Router → Application Service → Domain Policy → Repository / Adapter`，禁止在 HTML、ORM event、Celery Task 中分散重复授权/发布规则。以 PostgreSQL 作为业务状态真值；异步任务的重试/幂等/Outbox 要在后续阶段实现。WeKnora/docreader、Data-Juicer、LLM 仅通过定义明确的 Adapter 接入；没有真实外部服务时只允许开发/测试使用 MockAdapter，不得把它标记为真实结果。

项目必须具有：版本化迁移、稳定错误码、OpenAPI 契约、最小权限 RBAC + 工作空间隔离、用途级授权、结构化审计、可恢复执行、版本不可变、数据血缘；这些在各 P0 阶段逐步落地，不允许靠前端显示或假日志替代。

### 4. 本次只实施 P0-A，不跨阶段抢跑

审查并规划后，**实际编写 P0-A 工程骨架代码**：

- 目录骨架（`apps/api`、`apps/web` 或现有项目适配、`infra`、`tests`、`docs`）；V3.1 HTML 原文件作为只读原型留存。
- FastAPI 应用、`/health` 与 `/ready`（就绪性检查真实依赖，不把 mock 连接标成可用）、统一错误 DTO、环境配置、结构化日志、请求关联 ID。
- PostgreSQL / Redis / MinIO 本地 Compose 配置、SQLAlchemy/Alembic 初始化迁移、基础连接/会话管理。
- Python 锁定依赖，`.env.example`（只写占位，不写真密钥）、README 一键启动步骤、必要的 Makefile/脚本。
- pytest、ruff、类型检查、迁移 smoke test、CI 基本检查；在可用环境真实运行。
- 为后续 `identity`、`authorization`、`ingestion`、`pipeline`、`quality`、`dataset`、`lineage` 模块预留边界，但不要创造假“已实现”API。

如果发现已有工程能力，请尽量复用，交付等价的 P0-A 可验收结果。

### 5. 必须执行的验收与限制

本阶段至少验证：应用能启动、健康检查返回正确状态、DB 迁移可执行、配置缺失时错误可诊断、基础测试/静态检查通过、现有 V3.1 原型没有被覆盖。不能运行的项目要说明环境阻碍与未执行项，禁止写“通过”或捏造截图/报告。

**禁止**未经批准 `git push`、强制重置历史、删除现有用户数据、运行生产迁移或访问生产密钥。允许创建本地 Git 提交但需在报告中写提交 ID；如果仓库未初始化，先报告情况，不擅自覆盖现存版本管理。

交付 `docs/reports/P0-A_ACCEPTANCE.md`，包含：对应 FR/AC/TC、实际修改文件、可运行命令、测试命令与真实输出、失败与限制、API/迁移变化、下一步依赖、已知风险、需人工确认事项。

**完成 P0-A 后停止自动进入 P0-B，输出精简验收总结。** 不要仅输出实施建议，必须有实际可运行代码；但也不要以缺乏外部服务为由编造真实处理效果。

---

## 提示词二：复核上一阶段并继续实施下一阶段（每次复用）

请继续 CorpusFlow 项目开发。当前要实施的阶段是：`P0-B`（后续可替换为 `P0-C`、`P0-D`、`P0-E`、`P0-F`）。

1. 首先重新读取四份原始基线材料、`docs/plans/IMPLEMENTATION_PLAN.md`、`docs/plans/TRACEABILITY_MATRIX.md`、`docs/plans/OPEN_DECISIONS.md`，以及上一阶段 `docs/reports/P0-*_ACCEPTANCE.md`；实际审查 Git 状态和已有代码。
2. 检查前置阶段的可运行代码、迁移、接口、回归测试与未解决阻塞问题。发现严重缺陷先修复并记录，不直接在坏基础上扩建。
3. 严格按照《技术方案设计》第 9 节定义的当前阶段范围实现；对应需求和验收引用《需求分析与确认》的 FR/BR/AC/NFR/TC。保持模块边界、既有 API 向后兼容；重大变化写 ADR。
4. 每个完整功能都实现：领域规则 + 数据库/迁移 + API/DTO/OpenAPI + 必要 Worker/Adapter + 权限/用途策略 + 审计/错误码/幂等 + 正常与异常测试。不能仅实现页面按钮或内存模拟就声称完成。
5. 优先测试八项 V3.1 已修复缺陷不回归：内部研究不等于训练授权；N 资产产生 N Run；无关 RAG 不造证据；审核驳回不允许恢复；工程师不能发布；按 training/rag/evaluation 分用途；候选/计划不计 Asset；Build 配置/候选/审核/Manifest 一致且已发布版本不可变。
6. 真实运行适用的 `ruff`、pytest、DB/Worker/API 集成测试；UI 对接阶段再运行 Playwright 对着真实测试 API。不能运行的测试明确标记 NOT RUN，解释原因和复现命令。
7. 更新追踪矩阵、OpenAPI、迁移、README/ADR；输出 `docs/reports/<阶段>_ACCEPTANCE.md`，列出执行过的命令及结果、功能覆盖、遗留问题、下一阶段前置条件。
8. 当前阶段验收完毕后停止，不自动进入下一阶段，不推送远端，不删除用户文件。

### 各阶段完成边界（不可互相偷换）

- **P0-B IAM + Policy**：用户、Workspace/Membership、真实服务端身份/对象鉴权、许可证 Grant + Evidence；research/training/rag/evaluation/redistribute 用途独立，缺省 DENY，自审自发禁止。
- **P0-C Ingestion**：实际字节上传、SHA-256、对象存储、入库 Asset、批次、逐项失败隔离；DiscoveryCandidate/IngestPlan 与 Asset 完全分离。
- **P0-D Pipeline + QA**：版本化 DAG、N 资产 N Run、NodeRun/Artifact/日志、PDF+HTML 解析、DocumentVersion/Segment、质量异常与审核/重跑状态机、血缘边；审核通过不自动造成功产物。
- **P0-E Dataset + Release**：按用途选数、SFT 候选真实/明确标 mock 生成、来源组隔离、审核证据、构建快照、质量/授权门控、不可变 Manifest/Version、撤权影响处理。
- **P0-F Lineage/UI**：Sample→Source 双向追溯、真实统计与审计、V3.1 的 API Adapter/正式 UI 接入；运行真实 API 下的 Playwright E2E。

---

## 提示词三：阶段验收复查（在每阶段结束后使用）

请担任独立代码审查和测试负责人，**不要添加新业务功能**，仅审查最近完成的 CorpusFlow `<阶段>` 实现是否符合两份设计文档。核对 FR/BR/AC/NFR/TC；检查越权、许可证用途、数据统计口径、审核状态机、重试/幂等、构建快照、不可变版本、迁移安全、Secret 泄漏、OpenAPI 与代码漂移。运行实际可用的单测、集成测试、静态检查、迁移校验；给出 PASS/FAIL/NOT RUN 清单和每项证据。发现失败就修复当前阶段缺陷并重跑，严禁凭文字宣称通过。最后列出是否达到本阶段 Definition of Done，以及阻塞下一阶段的风险。

---

## 如果确实想一次性连续执行 P0-A～P0-F

建议先成功执行“提示词一”，确认项目技术环境和基本骨架可复现，再发送：

> 继续按 `docs/plans/IMPLEMENTATION_PLAN.md` 从 P0-B 依次推进到 P0-F。每阶段必须先通过该阶段的真实测试与迁移检查并生成独立验收报告，才允许继续；任何严重验收失败、安全/授权歧义或无法恢复的数据风险，立即停止并给出阻塞报告。不要跨阶段伪造完成度。保留 V3.1 原型；不得 push 远端或更改生产环境。完成后提供各阶段的代码、测试与最终需求追踪矩阵。

**注意**：一次连续执行容易受上下文、环境和依赖限制影响。分阶段提交、复核通常更可靠，尤其是权限/许可、任务状态机和数据集发布三个环节。
