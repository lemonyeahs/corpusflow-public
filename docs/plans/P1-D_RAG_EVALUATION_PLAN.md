# P1-D 真实 RAG 验证计划

基线：fb5fd48。范围仅限开发环境下游检索、评测与反馈；不进入 P2。

## 审查结论

复用 DatasetBuilder、不可变 DatasetVersion/Manifest、MinIO、Segment、用途授权、Outbox、Celery、QualityIssue 审核与显式重工。现有 Web 无真实下游验证页。P1-C 新迁移 head 为 0010。

本地 PostgreSQL 16 的 pg_available_extensions 不含 vector；包含未安装的 pg_trgm。实测 simple FTS 将“密钥轮换”视为整个词，查询“密钥”不能直接匹配。保持原数据库镜像，不安装不确定扩展；交付 PostgreSQL simple FTS 基线、Unicode 中日韩二元字符/英文 token BM25、二者 RRF 混合及可选确定性词项覆盖重排。它们是词法算法，不标记为语义向量。真实 Embedding/LLM 未配置时明确 ADAPTER_UNAVAILABLE，不调用外部服务。

Docker 原文件在 COPY 全部 API 后执行 uv sync，代码变化导致依赖层失效；构建后端 hatchling 未固定，网络超时反复下载。改为锁定构建后端、依赖层前置和 BuildKit 缓存，保留 uv --locked 校验；实际重建结果记入验收。

## 任务

| ID | 优先级 | 模块、变更与验收 |
|---|---|---|
| TASK-CF-P1D-001 | P0 | Docker 分层缓存/超时，真实构建；0011 RAG 迁移、0012 历史结构对齐及升降级 |
| TASK-CF-P1D-002 | P0 | IndexVersion/Chunk，读取真实发布 JSONL 并验证哈希/证据；Worker+Outbox 幂等建索引 |
| TASK-CF-P1D-003 | P0 | 检索策略、独立 Trace、当前授权过滤、撤权后旧 Trace 内容屏蔽；无证据不生成 |
| TASK-CF-P1D-004 | P0 | 从已发布 Evaluation 产品冻结 Suite，评测 Worker、Recall/Precision/MRR/nDCG/延迟，固定样本对照 |
| TASK-CF-P1D-005 | P0 | Feedback 关联 Trace/Case/Segment/QualityIssue，复用审核与显式重工，新版本再建索引复测 |
| TASK-CF-P1D-006 | P1 | Web 下游验证、类型/API 契约、真实 Docker E2E 和报告 |

## 数据与 API

新增 rag_index_versions、rag_chunks、retrieval_traces、rag_evaluation_suites、rag_evaluation_runs、rag_feedback。索引冻结 DatasetVersion 内容哈希、配置和 Chunk 定位；Trace 保存独立查询/算法/分数/引用；Suite 固定发布评测产品与评注。历史完成结果追加保存，不改旧发布文件。

API 前缀 /api/v1/rag：capabilities、indexes、queries、traces、suites、evaluations、feedback。所有操作限定 workspace；工程师建索引/评测，审核员创建已核对 Suite、复核使用原 QualityIssue API。向量与生成未配置则明确不可用。

## 评测与风险

使用原创合成技术说明 fixture，通过真实 HTML parser/Worker 和 RAG/Evaluation Builder 发布。问题与证据可复现，标明机器制作参考、开发审核身份，不能冒充业务专家标注。固定评测集比较 FTS、BM25、hybrid 和重排；无答案单独统计。未有真实模型不评估回答正确性/faithfulness。

退出标准：真实 PostgreSQL/MinIO/Worker/Web；用途与空间拒绝、撤权隔离、重复索引、查询独立性、指标手算测试、反馈重工新版本；pytest/ruff/mypy/迁移/OpenAPI/Web/Playwright 全部记录真实结果。失败保留诊断，不自动进入下一阶段。

复核补充：现有旧库的 P1-A/C JSON 类型、时间戳约束和 run_id 索引存在漂移，新增 0012 前向修复；11 张表迁移前后逻辑行摘要相同。迁移测试包含模拟旧列结构与缺失时间戳阻断，不只验证空库。
