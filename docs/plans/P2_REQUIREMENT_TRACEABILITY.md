# P1/P2 本轮需求与证据映射

所有 REAL 表示已执行列出的本地验证，不代表生产门禁。完整阶段状态见 CORPUSFLOW_FINAL_ACCEPTANCE.md。

| 需求 | 模块 / 持久对象 | 验证 / 证据 | 状态 |
|---|---|---|---|
| 真实上传、解析、清洗和去重 | ingestion / pipeline / DocumentVersion / Segment | p0-h、p0-i、p1-a Web；全量 pytest | REAL |
| 四类产品审核、发布、下载、血缘 | DatasetBuilder / DatasetVersion / MinIO / lineage | p1-b/c/d Web；P1-B_DATASET_SAMPLES | REAL |
| 历史检索基线可复现 | rag / RagEvaluationSuite / Run | verify_p1_reproducibility.py，31 查询六组 | REAL |
| 三组可追溯演示资料 | Asset / Run / NodeRun | prepare_demo_manifest.py、DEMO_EVIDENCE.json | REAL 独立链路，整体 PARTIAL |
| 实际 Embedding 与版本 | embedding Adapter / tools/semantic | test_embedding.py、P2-A_PLATFORM_EVIDENCE | REAL |
| 持久向量、增量复用、重复消息 | RagChunk.embedding / IndexVersion / Worker | verify_p2_semantic.py；26/26 复用 | REAL |
| 查询与历史撤权 | rag.visible_trace / purpose policy | verify_p2_semantic.py、test_rag_policy.py | REAL |
| 混合召回及负面样例 | RRF / RetrievalTrace / EvaluationRun | P2-A 四组实测，无阈值无答案误命中 4/4 | REAL |
| 生产规模向量索引 | 当前为 JSONB 精确余弦、上限 5000 | pgvector/ANN 未部署 | NOT IMPLEMENTED |
| 异步证据回答、配置与 Trace | GenerationAdapter / GenerationRun / Outbox | verify_p2_generation.py；实际调用 2 次 | REAL / LIMITED |
| 预算、重投不重复计费 | DB 预留 / Worker 锁 / 0017 | test_generation.py、真实重复任务及 DB guard | REAL |
| 引用闭集与无证据拒答 | answer_contract / generation.visible | 单元测试、实际引用和拒答 | REAL；语义正确性非自动证明 |
| 文档提示注入 | 固定系统指令、无工具、引用验证 | 1 条真实模型拒答 | LIMITED，通用防护未证明 |
| 独立语义重排与评分拆分 | RerankerAdapter / RetrievalTrace | verify_p2_reranker.py；4×31 查询 | REAL bi-encoder；非 Cross-Encoder |
| 人工正确性、支持性、分歧 | RetrievalReview / API / Web | test_retrieval_review、verify_p2_answer_reviews、p2-generation Web | REAL 工作流 |
| 真实专家及完整回答评测 | 需要真实参与者和调用资源 | 无参与者；未跑全 31 条生成 | NOT RUN |
| 扫描件 OCR、定位及版本复用 | OCRParserAdapter / Worker / MinIO | raster.pdf、verify_p2_ocr.py、p2-c Web | REAL / LIMITED |
| 多栏、表格公式、中文版面 | 尚未完成专业 Adapter 与参考标注 | docreader ListEngines 不算效果证据 | NOT_EVALUATED |
| 候选→计划→审核→任务 | collection / IngestPlan / Outbox | verify_p2_collection.py，职责分离/驳回/幂等 | REAL |
| SSRF、大小和超时门控 | SafeFetcher / allowlist / DNS IP pinning | test_acquisition.py；真实 Fake-IP 拒绝 | REAL 拒绝路径 |
| DOI/URL 公网成功导入 | SafeFetcher / Worker / Asset | 当前非公网 DNS，零 Asset、零自动授权 | BLOCKED |
| 真正执行中的 Worker 强杀 | 独立 DB/Redis 前缀/自建容器 | verify_p2_worker_crash.py；0→26 自动恢复 | REAL |
| 数据库备份恢复 | pg_dump/pg_restore / 0017 | verify_local_restore.py；14 触发器和 fixture 行 | REAL 本地 fixture |
| OIDC / HA / 生产压力 / 全量灾备 | 尚无正式部署验证 | 未访问生产 | NOT RUN |
| 原型、已发布文件保护 | git / immutable triggers / S3 | 迁移和业务回归；原型无改动 | REAL |
| 敏感配置不入 Git | SecretStr / ignored local env | 提交前实际值扫描 0 命中，权限 0600 | PASS |
