# 演示架构

React/Vite → FastAPI Router → Application Service/Policy → PostgreSQL。

PostgreSQL Outbox → Dispatcher → Redis/Celery → Parser/Processing Adapter → MinIO 产物与 PostgreSQL 业务记录。

DatasetBuilder → 审核/用途门控 → JSONL/Manifest 不可变发布 → RAG Index/Trace → EvaluationRun → QualityIssue → 审核和显式重工。

模型缓存/第三方 docreader 是外部资源，未接入的资源不计入 REAL 能力。生产身份、HA 与真实生产负载仍未通过。数据库是状态真值；前端不决定最终授权。
