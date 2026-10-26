# 现场演示数据清单

本清单只记录可由 API 或数据库复核的对象类别，不生成新的业务数据。

| 类别 | 真实来源 | 校验方式 |
|---|---|---|
| Source / Asset | 当前开发 workspace PostgreSQL | `GET /api/v1/sources`、`GET /api/v1/assets` |
| 原始对象 | MinIO/S3 开发桶 | Asset lineage 的 300 秒签名 URL、SHA-256 |
| DocumentVersion / Segment | PostgreSQL | `/assets/{asset_id}/lineage-view` |
| PipelineRun / NodeRun | PostgreSQL | `/pipeline-runs/{run_id}` |
| DatasetVersion / Manifest | PostgreSQL + MinIO | 数据产品版本与下载 API |
| RAG 案例 | PostgreSQL | `/demo/cases`；缺失则显示 `MISSING` |

演示环境不得把 `.env`、Token、对象存储密钥、模型凭证或未授权原文纳入清单。历史对象跨 workspace 不共享。
