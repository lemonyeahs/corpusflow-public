# P0-E Dataset + Release 验收

日期：2026-10-24（Asia/Shanghai）  
任务：TASK-CF-005。范围：FR-008/029～036、BR-BUILD、AC-BUILD、TC-16～21。

## 实现

- `dataset_definitions`、`dataset_builds`、`dataset_build_inputs`、`candidate_samples`、`sample_evidence/reviews`、`dataset_versions`、`dataset_version_samples`。
- Preview 按用途重检 grant 并返回 included/excluded；Build 冻结规范化 config hash、输入 segment/content hash；候选逐条审核。
- Validate 生成服务端 gate；发布要求 validated、候选已批准、审核人与发布人职责分离；版本号唯一，manifest/content hash 固定，重复版本幂等返回。

## 实测

- `scripts/verify_business_loop.py`：training preview 命中 3 段；3 个候选由独立 reviewer 批准；validate `ok=true`；发布 `1.0.0` 状态 `published`，生成 manifest/content SHA-256。
- 同一构建未允许自审自发；发布后版本内容列没有更新接口，历史样本通过 FK 保留。
- `0003_immutable_release` PostgreSQL trigger 实测拒绝已发布版本的 manifest hash 更新。

## 结论与边界

P0-E 门禁通过，可进入 P0-F。JSONL/Parquet 对象物化、来源组至少三组的严格 split 算法、撤权后的已发布可用性处置仍需增强；当前版本门控与不可变数据库记录已落地。
