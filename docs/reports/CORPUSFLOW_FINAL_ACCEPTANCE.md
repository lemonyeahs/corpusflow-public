# CorpusFlow P1/P2 综合验收

日期：2026-10-25；起点 `81bb913`，本轮最终数据库 `0017_generation_guards`。

**开发/演示环境：已实现范围 CONDITIONAL PASS。完整 P2 目标：FAIL，尚有未完成项。生产就绪：FAIL。** 本报告替代早期组件阶段结论；不把局部测试通过当作专业文档、外部采集、专家评测和生产部署全部完成。

## 能力与阶段矩阵

| 阶段/能力 | 状态 | 实际依据及限制 |
|---|---|---|
| P0/P1 上传、解析、清洗、质量、四类产品、发布下载、血缘 | REAL / CONDITIONAL PASS | 真实 Docker Web、PostgreSQL、MinIO、Worker 回归；保留开发认证及既有已知限制 |
| P1 检索复现 | REAL / PASS | 同一 31 条查询六组历史实验对照；保留 1/4 无答案误命中 |
| 系统演示 | REAL 独立链路 / PARTIAL | 三组原件 SHA、真实 Run/NodeRun、数据清单和截图；未声称三组在单一空间贯通 |
| P2-A 语义检索 | REAL / CONDITIONAL PASS | 本地 MiniLM、持久向量、异步构建、增量复用、RRF、撤权、Web；有界精确搜索，非 pgvector/ANN |
| P2-B 模型证据回答 | REAL / LIMITED | 已授权外部服务实际 2 次，精确引用及拒答；无证据 0 调用，数据库预算保护 |
| P2-B 语义重排 | REAL / CONDITIONAL PASS | 独立本地 bi-encoder Adapter，31 条四组实测；不是专业 Cross-Encoder，未证明效果提高 |
| P2-B 人工评测工作流 | REAL | 多人记录、分歧、检索/回答分开、真实 API/Web；专家实际参与 NOT RUN |
| P2-C 图片型 PDF OCR | REAL / LIMITED | Docker 中 Poppler/Tesseract、真实位图、文字/页码/坐标、版本与幂等 |
| P2-C 多栏/公式/复杂表格/中文 OCR | NOT_EVALUATED | 未完成可靠专业版面适配；docreader 可达不能当作解析验收 |
| P2-C URL/DOI/计划/审核/SSRF | REAL 拒绝路径 / BLOCKED 成功路径 | Fake-IP DNS 返回 198.18.0.117，按非公网地址拒绝；未放宽门控，无伪造 Asset |
| 运行中 Worker 强杀与恢复 | REAL / PASS | 自建隔离 Worker 实际 INSERT 时强杀，回滚 0，自动恢复 26 个片段 |
| PostgreSQL 备份恢复 | REAL / PASS（本地 fixture） | pg_dump/pg_restore、0017、fixture 行与 14 个触发器恢复 |
| OIDC、多节点 HA、生产负载、灾备 | NOT RUN / 未完成 | 开发身份不是生产认证；未声称生产就绪 |
| 公网采集→复杂解析→发布→模型→专家全链路 | BLOCKED / NOT RUN | 外网成功路径、复杂解析与真实专家缺失；本地上传不替代外网成功 |

正式统计来自数据库、实际对象字节或模型结果；未把原型 DEMO 与测试断言分数混入生产质量统计。

## 架构、迁移和 API

React/Vite → FastAPI Router → Application Service/Policy → PostgreSQL。PostgreSQL 为业务真值；Outbox → Dispatcher → Redis/Celery，MinIO 存原始文件、解析中间物和不可变发布文件。本地独立 MiniLM 服务供 Embedding/Reranker Adapter 调用；外部生成仅限显式授权的测试 workspace；网络采集由受控 Adapter 执行。第三方内部数据对象不替代业务模型。

| 迁移 | 变化 |
|---|---|
| 0013_semantic_embeddings | RagChunk 可空向量，旧词法索引保留，索引冻结模型/维度 |
| 0014_retrieval_reviews | 不可覆盖的评分记录与 reviewer/Trace/版本 |
| 0015_ingest_plans | 采集计划、候选、冻结配置和审核执行状态 |
| 0016_evidence_generation | GenerationRun、配置、结果、调用预留 |
| 0017_generation_guards | 终态回答、配置、已消耗调用预留不可重置/删除 |

新增/扩展：`rag/indexes`、`rag/queries`、`rag/evaluations` 的语义参数；`rag/reviews` 与 Trace 评分；`rag/answers` 异步生成及详情；`collection/doi-metadata`、`collection/candidates`、`collection/plans` 及审核详情。完整契约见 `docs/api/openapi.json`。角色、workspace、用途与质量由后端执行，隐藏按钮不构成保护。

本轮关键源码：adapters 下 embedding、reranker、generation、answer_contract、ocr、acquisition；services 下 rag、generation、retrieval_review、collection；worker/tasks 与 celery_app；Web RagPage、CollectionPage；独立 tools/semantic 锁定环境。具体文件清单可用下述提交和 `git diff --name-only 81bb913..HEAD` 审阅。

## 最终执行结果

全部本地执行，未远程 push，远程 CI NOT RUN。`.local/p2/` 是本机原始日志目录；提交的 `*_EVIDENCE.json` 保留可分享的业务证据，不含登录 Token。

| 命令/验证 | 结果 | 证据 |
|---|---|---|
| `EMBEDDING_ENDPOINT=http://127.0.0.1:58110 .venv/bin/python scripts/verify_p1d_environment.py` | **92 passed，0 skipped** | final-pytest.log；含 7 个真实集成测试 |
| `make check` | Ruff PASS、117 文件格式 PASS、Mypy 48 文件 PASS、85 passed / 7 deselected | final-check.log；此处 deselected 为另行执行的集成测试 |
| `.venv/bin/alembic check` | No new upgrade operations detected | final-alembic.log；全量测试另覆盖临时库升级/降级/重升级 |
| 前端 typecheck / lint / build | PASS | TypeScript/ESLint/Vite 实际运行，构建 1950 模块 |
| `npm --prefix apps/web run e2e` | **11 passed，1.2 分钟** | final-playwright.log，真实 Docker API，无 Mock 替代 |
| 回答评分新增断言复验 | **1 passed，2.6 秒** | answer-review-playwright.log；包含真实答案/引用/拒答/评分，0 新模型调用 |
| `verify_p1_reproducibility.py` | PASS | 六组指标与分母一致，负面结果保留 |
| `verify_p2_semantic.py` | PASS | P2-A_PLATFORM_EVIDENCE.json；授权、增量、不可变、同集比较 |
| `verify_p2_reranker.py` | PASS | P2-B_RERANKER_EVIDENCE.json；4×31 查询 |
| `verify_p2_generation.py` | PASS（限定范围） | P2-B_GENERATION_EVIDENCE.json；2 次真实模型调用 |
| `verify_p2_answer_reviews.py` | PASS | P2-B_ANSWER_REVIEW_EVIDENCE.json；评分幂等/冲突，终态与预算不可修改 |
| `verify_p2_ocr.py`、`verify_p2_collection.py` | OCR PASS；采集拒绝路径 PASS | P2-C_OCR_PLATFORM_EVIDENCE.json、P2-C_COLLECTION_DENIAL_EVIDENCE.json；公网成功路径 BLOCKED |
| `verify_p2_worker_crash.py` | PASS | P2-C_WORKER_RECOVERY_EVIDENCE.json；未终止共享 Worker |
| `verify_local_restore.py` | PASS | P2-C_RESTORE_EVIDENCE.json；只恢复自己创建的随机库 |

2253 条弃用警告主要来自既有 datetime.utcnow 与 Starlette/httpx 测试客户端，未隐藏。先前 Playwright 并行共享 fixture 文件导致 10 passed / 1 failed，改为单 Worker 后全套通过，未删除断言。首次故障脚本因旧 Worker 镜像参数不兼容失败，重建后才完成真实强杀恢复。早期 OpenAPI 快照未更新导致契约失败，更新导出并复验通过。最终部署重建期间误并行运行测试，MinIO multipart 收到临时 502（91 passed / 1 failed）；保留 redeploy-storage-failure.log，等待部署完成后全量复验 92 passed。最后修复可选答案字段引起旧评分幂等冲突，补充后端断言并复验两项真实评分 Web：2 passed，3.9 秒。

## 真实效果、性能与成本

31 条冻结原创说明问题：27 有答案、4 无答案，二值标签。不是密码学论文全集，也不是独立专家基准。

| 检索方法（K=3） | Recall | Precision | MRR | nDCG | 无答案误命中 |
|---|---:|---:|---:|---:|---:|
| BM25 | 1.000 | 0.346 | 1.000 | 1.000 | 1/4 |
| 向量，不设拒答阈值 | 1.000 | 0.346 | 0.938 | 0.954 | 4/4 |
| 向量，阈值 0.5 | 0.778 | 0.272 | 0.778 | 0.778 | 0/4 |
| 语义混合 | 1.000 | 0.346 | 0.981 | 0.986 | 1/4 |
| BM25 + 本地语义重排 | 1.000 | 0.346 | 1.000 | 1.000 | 1/4 |

语义重排 BM25 p50 约 33.52 ms，词法基线 4.24 ms；混合重排 K=3 的 p50/p95 约 53.53/101.61 ms。没有证明质量提升。26 向量初次构建约 208 ms，505 输入 Token、0 截断、39,936 float32 原始字节；不是 JSONB 磁盘实占或负载 SLA。新版本实测复用 26/26。

LLM 实际 2/10 次：AES 回答成功，输入/输出 360/59 Token、8292 ms；提示注入样本拒答，312/15 Token、1562 ms；无证据直接拒答无调用。请求限制每次 512 输出 Token。供应商价格未知，货币成本 NOT_MEASURED；返回模型名称并非来源证明。完整 31 条生成对照 NOT RUN，未超预算。

OCR 真正图片型输入提取 “CorpusFlow OCR evidence: AES block size is 128 bits.”。内置解析该输入应失败，OCR 成功且重复执行不增加文档版本。复杂表格/公式/中文/多栏正确率 NOT_EVALUATED。

## 正常、异常和交付证据

- 正常：P0-H Web 上传 PDF→异步处理→候选审核→不同身份发布→MinIO JSONL 下载/哈希→血缘；P1-B 四类 Builder 回归；P1-C 质量报告与不可变比较；P1-D 检索/评测/反馈重工。
- 异常：损坏 PDF 的实际错误、审核驳回不可恢复、用途独立检查、越权、快照失效、重复投递、不变版本、当前及历史检索撤权；模型无证据拒答、评分目标错配和终态修改拒绝。
- 故障：SQL 写入时强杀隔离 Worker，未提交行回滚，Redis 自动重投恢复 26 行；不是任务早已结束后的形式重启。
- 数据产品样例：`P1-B_DATASET_SAMPLES.md`、`P1-D_EVIDENCE.json` 及本轮 `P2-A_PLATFORM_EVIDENCE.json` 记录真实发布/索引关系，未覆盖历史文件。生成回答样例见 P2-B_GENERATION_EVIDENCE.json。
- 演示：`docs/demo/DEMO_GUIDE.md`、DATA_MANIFEST、SCRIPT、ARCHITECTURE、RESULTS 和 DEMO_EVIDENCE.json。截图 `.local/demo/evidence-answer-detail.png` 来自实际 Web 页面；不把旧 V3.1 原型当作真实系统截图。

## 启动、回滚与数据保护

启动顺序和命令见根 README、tools/semantic/README.md。本机先启动独立离线模型，再启动 Compose API/Worker/Dispatcher，最后 Vite。模型为空时功能明确不可用。外部生成默认为 disabled，不把密钥放入前端或 Git。

回退优先禁用新增能力、停止新任务并保留数据库/对象；不能对业务库直接 downgrade base。0013–0017 回退存在向量、计划、评分、回答或保护丢失风险，须先停写、备份并导出。迁移往返只对随机测试库执行。未覆盖 V3.1、历史数据集文件；未访问生产或删除用户数据。故障清理只删除脚本自己创建的临时数据库/容器，不删共享卷。

## 剩余风险与后续顺序

1. **高 / BLOCKED**：外网成功采集。当前非公网 DNS 结果必须拒绝；需要合规正常 DNS/出口与许可明确的目标文档后复验，不采用绕过地址校验的代理。
2. **高 / 未完成**：复杂专业 PDF、表格公式、多栏、中文 OCR；需要许可明确且有人工作为参照的资料，以及 docreader/专业解析器适配与效果对照。
3. **高 / NOT RUN**：真正领域专家与完整回答评测。已交付评分工作流，不能代替专家参与；更大模型实验需新预算，当前只用 2 次。
4. **高 / 生产阻断**：正式 OIDC/SSO、密钥轮换、网络隔离、HA、全量备份灾备、依赖安全扫描、镜像 SBOM、生产压力与恢复指标。当前开发认证不可对公网开放。
5. **中**：精确向量最多 5000 Chunk、模型最多 128 Token；需要 pgvector/ANN、独立验证集与吞吐测试后扩容。bi-encoder 重排非专业 Cross-Encoder，当前没有提升证据。
6. **中**：对象成功而 SQL 失败可能留下采集孤儿对象，已有可诊断计划 ID，自动安全 GC 未实现；MinIO 灾备及全链路故障组合未新增验证。
7. **中**：评分历史和评测报告 Web 仍以较长结构化详情为主；大型任务的分页与聚合交互需优化。弃用警告需后续兼容升级。

先解决数据出口/许可、专业解析和专家评测，再验证模型效果与生产身份/灾备；不宣称通过完整 P2 或自动进入后续阶段。

需求、模块与测试映射见 `docs/plans/P2_REQUIREMENT_TRACEABILITY.md`。本轮本地提交见 `P2_LOCAL_COMMITS.md`。提交粒度不等于阶段 PASS；没有远程 push。
