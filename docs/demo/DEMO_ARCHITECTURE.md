# 演示架构

React/Vite → FastAPI Router → Application Service/Policy → PostgreSQL。

PostgreSQL Outbox → Dispatcher → Redis/Celery → Parser/Processing Adapter → MinIO 产物与 PostgreSQL 业务记录。

DatasetBuilder → 审核/用途门控 → JSONL/Manifest 不可变发布 → RAG Index/Trace → EvaluationRun → QualityIssue → 审核和显式重工。

模型缓存/第三方 docreader 是外部资源，未接入的资源不计入 REAL 能力。生产身份、HA 与真实生产负载仍未通过。数据库是状态真值；前端不决定最终授权。


P2 增量：本地独立 MiniLM 服务 → EmbeddingAdapter / RerankerAdapter → PostgreSQL 不可变向量与 Trace；受控 GenerationRun → Outbox/Worker → 外部兼容模型 → 引用校验 → 回答/人工评测历史。OCR 已在 Worker 镜像运行。Candidate → IngestPlan → 不同身份审核 → 安全网络获取 → Asset；本机公网下载成功路径 BLOCKED，不能演示为完成。
