# DPO 数据流水线

~~~mermaid
flowchart LR
  A[Asset / Segment] --> B[训练授权校验]
  B --> C[PreferenceSample 导入]
  C --> D[多人盲式成对标注]
  D --> E{冲突/平局?}
  E -- 是 --> F[UNCERTAIN/TIE，复核阻断]
  E -- 否 --> G[独立审核 APPROVED]
  G --> H[DpoBuilder]
  H --> I[CandidateSample + Build 快照]
  I --> J[质量/证据/授权门控]
  J --> K[staging JSONL + Manifest]
  K --> L[DatasetVersion 不可变发布]
  L --> M[签名下载与血缘]
~~~

## 持久化设计

preference_samples 保存 Prompt、A/B 回答、证据、模型配置、状态、审核人和已发布版本；preference_annotations 保存每个标注者的一次不可变选择。DPO 构建继续使用 dataset_builds、candidate_samples、sample_reviews、dataset_versions 和 dataset_version_artifacts，因此发布、质量、Outbox、Manifest 和下载权限不分叉。

## API

- GET /api/v1/dpo/overview
- POST /api/v1/dpo/preferences/import
- GET /api/v1/dpo/preferences
- GET /api/v1/dpo/preferences/{id}
- POST /api/v1/dpo/preferences/{id}/annotations
- POST /api/v1/dpo/preferences/{id}/review
- POST /api/v1/dpo/builds

通用构建校验、质量报告、版本发布、Manifest、下载和血缘 API 继续复用现有接口。

## 迁移

0019_dpo_preferences 新增两张表、索引、workspace/sample 唯一键和标注不可变触发器。回滚只允许在隔离数据库执行；业务数据库回滚前必须备份并导出 DPO 标注和发布 Manifest。
