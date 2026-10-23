# 实施计划

严格按 P0-A → P0-B → P0-C → P0-D → P0-E → P0-F 顺序推进。本轮只执行 TASK-CF-001，完成后停止，后续均 TODO。以下遵循技术方案第 10 节任务模板；未来命令为计划，不代表已有测试。

### TASK-CF-001｜P0-A 工程骨架
- 对应需求：NFR-01/06/08、TC-25/26/28（部分）
- 优先级/前置：P0；依赖 无
- 模块/文件改动：apps/api/core、api/health、db、infra、tests；本次实施
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：仅 alembic_version；0001_p0a upgrade/downgrade；新增迁移需验证升降级，不对生产自动执行。
- API 变更：GET /health、GET /ready；统一错误 DTO、OpenAPI；实现时同步 OpenAPI。
- Worker/外部依赖：PG/Redis/S3 真实超时探测；Celery 仅依赖锁定，不运行任务
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then 依赖全通才 ready 200；缺配置明确失败；依赖失败 503；原件哈希不变。
- 测试命令：make check；make integration；make up
- 交付证据：docs/reports/P0-A_ACCEPTANCE.md
- 不在范围：IAM 与全部业务 API

### TASK-CF-002｜P0-B IAM + Policy
- 对应需求：FR-010/027/028/041；BR-AUTH-*、BR-GOV-02/04；AC-IAM-*；TC-05/06/07/08/19
- 优先级/前置：P0；依赖 TASK-CF-001
- 模块/文件改动：modules/identity、authorization；service/policy/repository 与 DTO
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：users/workspaces/memberships/license_evidence/license_grants/audit_events 与最小 Source/Asset FK 引用表（OD-18）；事务与约束，独立迁移；新增迁移需验证升降级，不对生产自动执行。
- API 变更：auth/session、auth/me、workspaces、authorization/decisions；401/403/422；实现时同步 OpenAPI。
- Worker/外部依赖：OIDC 或开发身份；开发身份禁止生产；撤权持久事件
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then 无 grant 默认 deny；用途不继承；跨空间与同人自审自发阻断。
- 测试命令：后续 pytest tests/unit tests/integration -k policy
- 交付证据：TODO 身份/许可测试报告
- 不在范围：上传、流水线、生产身份配置自动推断

### TASK-CF-003｜P0-C Ingestion
- 对应需求：FR-002/003/011～016；BR-AUTH-02；AC-ING-*、AC-ASSET-*；TC-01～05/10
- 优先级/前置：P0；依赖 TASK-CF-002
- 模块/文件改动：modules/ingestion/catalog/discovery、adapters/storage、上传 DTO
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：sources/blobs/assets/upload_sessions/batches/items/candidate/plan；hash、FK、索引、可回滚迁移；新增迁移需验证升降级，不对生产自动执行。
- API 变更：uploads/init/complete、ingest-batches、assets/stats；ASSET_NOT_READY/DUPLICATE_CONTENT；实现时同步 OpenAPI。
- Worker/外部依赖：S3 multipart/校验/病毒扫描；真实字节；按文件失败隔离
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then 选中不建 Asset；3 文件中间失败保留其余；列表统计同口径；重复请求幂等。
- 测试命令：后续 pytest tests/integration -k ingestion
- 交付证据：TODO 三文件/对象哈希与统计证据
- 不在范围：URL/DOI 真实采集（P1）

### TASK-CF-004｜P0-D Pipeline + QA
- 对应需求：FR-005/006/017～026/042；BR-RUN-*；AC-RUN-*、AC-QA-*、AC-STRUCT-*；TC-09～15
- 优先级/前置：P0；依赖 TASK-CF-003
- 模块/文件改动：modules/pipeline/quality/catalog、worker、parser/processing adapters
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：templates/versions/runs/node_runs/artifacts/DV/segments/issues/reviews/outbox/idempotency；唯一键与 revision；新增迁移需验证升降级，不对生产自动执行。
- API 变更：pipeline-runs/batches/resume、documents/segments、quality/reviews；409 RUN_REVIEW_BLOCKED；实现时同步 OpenAPI。
- Worker/外部依赖：Celery/Redis、PG Outbox/lease、重试退避和幂等；Mock 显式测试模式
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then N=3 恰好 3 Run；驳回不可恢复；审批后 Worker 重跑成功才新产物；重启恢复。
- 测试命令：后续 pytest tests/integration -k "pipeline or quality or recovery"
- 交付证据：TODO PDF/HTML 真解析、节点与恢复报告
- 不在范围：全面 OCR、Data-Juicer 全量算子、生产高可用

### TASK-CF-005｜P0-E Dataset + Release
- 对应需求：FR-008/029～036；BR-BUILD-*、BR-AUTH-03/04；AC-BUILD-*；TC-16～21
- 优先级/前置：P0；依赖 TASK-CF-004
- 模块/文件改动：modules/dataset、generation adapter、policy 发布门控
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：build/input/candidate/evidence/review/version/version_samples；冻结 hash、唯一版本与不可变列；新增迁移需验证升降级，不对生产自动执行。
- API 变更：dataset-builds/preview/create/validate、candidate reviews、datasets/versions；实现时同步 OpenAPI。
- Worker/外部依赖：生成 Adapter；Mock 只限开发/测试且禁止真实发布；S3 先物化 PG 后提交及补偿
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then 配置变化重建；逐候选证据审核；来源不跨 split；并发幂等只一版本；历史不可变。
- 测试命令：后续 pytest tests/integration -k "build or publish"
- 交付证据：TODO 并发发布、撤权、对象一致性测试
- 不在范围：Pretrain/RAG/Eval/Parquet（P1）、DPO（P2）

### TASK-CF-006｜P0-F Lineage/UI 对接
- 对应需求：FR-001/004/007/043；BR-GOV-*；AC-LINEAGE-01、AC-DASH-01；TC-15/24/27/28
- 优先级/前置：P0；依赖 TASK-CF-005
- 模块/文件改动：modules/lineage、统计 API、apps/web API Adapter、E2E
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：lineage_edges、作用域索引；只读查询授权与审计；新增迁移需验证升降级，不对生产自动执行。
- API 变更：lineage/{type}/{id}、统计；统一过滤/as_of/来源标识；实现时同步 OpenAPI。
- Worker/外部依赖：仅连接已验收后端；DEMO/REAL 明确，不自动降级演示
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then Sample→Source 逐级可查；跨空间不可见；GET 确认后显示完成；刷新状态保留。
- 测试命令：后续 pytest；Playwright tests/e2e
- 交付证据：TODO 全闭环 Trace 与报告
- 不在范围：P1 检索、完整十页重设计

### TASK-CF-007｜P1-A 外部适配扩展
- 对应需求：FR-009/014/026/037～040；AC-RAG-*；TC-22/23/24
- 优先级/前置：P1；依赖 TASK-CF-006
- 模块/文件改动：integrations/verification、parser/processing/search adapters
- 不变式：默认拒绝用途与权限；PG 为业务状态真值；成功必须有真实证据；历史原件不覆盖。阶段专属约束见验收步骤。
- 数据变更：rag_queries/hits/feedback 与扩展产物 schema，独立迁移；新增迁移需验证升降级，不对生产自动执行。
- API 变更：rag/search/feedback、导出 API，授权与索引快照；实现时同步 OpenAPI。
- Worker/外部依赖：锁定 docreader/Data-Juicer/LLM 协议版本、超时/重试/结构校验
- 验收步骤：Given 前置阶段通过，When 执行正常及异常请求，Then 零证据拒答；query 变更旧快照失效；撤权阻断；金标集与适配契约。
- 测试命令：后续 adapter contract tests + retrieval E2E
- 交付证据：TODO POC/许可评估/金标报告
- 不在范围：DPO（P2）、P0 一次性接全组件
