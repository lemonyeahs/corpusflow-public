# CorpusFlow P1-B 多类型数据产品计划

日期：2026-10-24  
基线：`356f951 feat: add P1-A document processing pipeline`  
范围：预训练语料、RAG 知识片段、评测数据集；复用 SFT 构建和发布链路，不进入 P1-C/P1-D，不实现在线向量检索或 DPO。

## 现状复用

P0-G 已提供 `DatasetBuild`、`CandidateSample`、`DatasetVersion`、MinIO staging/immutable objects、Manifest、用途授权、审核职责分离、幂等版本发布和 lineage。P1-A 已为 Segment 保留定位/token/章节信息。本轮不新增三套发布系统，也不修改已有发布记录。

## 任务拆分

| 任务 | 优先级 | 依赖 | 实现 | 验收 |
|---|---|---|---|---|
| `TASK-CF-301` Builder 接口与产品注册 | P0 | P0-G/P1-A | `DatasetBuilder`、Sft/Pretrain/Rag/Evaluation builder、产品类型 API | Schema 和用途映射测试 |
| `TASK-CF-302` 预训练语料 | P0 | 301 | 按来源连续组织、去重/长度过滤、source-group 划分、token 统计 | 真实 JSONL/Manifest/血缘 |
| `TASK-CF-303` RAG 片段 | P0 | 301、Segment 定位 | token/char chunk、overlap、来源定位、all 划分 | 不同配置不同结果、反向追踪 |
| `TASK-CF-304` 评测数据 | P0 | 301、人工候选 | question/reference/evidence Schema、重复题检测、证据门控 | 缺证据阻断、真实样本发布 |
| `TASK-CF-305` 统一物化与 Web | P1 | 302-304 | 产品专属 JSONL、Manifest、质量报告、前端配置/预览 | MinIO 发布下载和 Playwright |
| `TASK-CF-306` 回归与交付 | P0 | 301-305 | P0/P1-A 回归、跨 workspace、幂等/不可变检查、样例报告 | P1-B 验收报告 |

## 统一数据流

`Segment → 产品 Builder → CandidateSample(payload + evidence_ids) → SampleReview → DatasetBuild.validate → DatasetMaterializer → immutable JSONL/Manifest → DatasetVersion → signed download`。

Builder 只负责产品专属转换和质量筛选；授权、审核、版本状态、对象存储、Manifest、Outbox、审计和 lineage 继续使用现有共享服务。

## Schema 与策略

- `sft.v1`：`messages`，用途 `training`，按 source group 划分。
- `pretrain.v1`：`text`、`evidence_ids`、metadata，按 source 连续组织，按 source group 划分。
- `rag.v1`：`text`、`source_id`、`asset_id`、`document_version_id`、`segment_id`、`location`、chunk 参数，默认 `all`，不套用 SFT 比例。
- `evaluation.v1`：`question`、`reference_answer`、`evidence_ids`、`question_type`、`difficulty`、`domain`、`source_ids`、review/quality 状态，默认 `all`。

每种产品的 `purpose` 固定映射为 training/training/rag/evaluation。发布重新校验 payload Schema、evidence、workspace、用途授权、审核人和发布人分离。构建配置写入 `DatasetBuild.config_json` 并通过 `config_hash` 固化；版本发布前要求验证快照哈希一致。

## API 差异

- `GET /api/v1/dataset-products/types`：产品类型、用途和 Schema 版本。
- `POST /api/v1/datasets`：支持 `sft|pretrain|rag|evaluation`。
- `POST /api/v1/dataset-builds/preview`：按产品类型和用途返回授权纳入/排除。
- `POST /api/v1/dataset-builds`：根据 Dataset 的产品类型调用 Builder，保存配置、过滤原因和指标。
- `GET /api/v1/dataset-builds/{id}/candidates`：返回产品 payload 预览。
- `GET /api/v1/dataset-builds/{id}/quality-report`：返回候选、过滤、审核和 Builder 指标。
- 既有 validate/publish/manifest/download/lineage API 继续复用，产品字段写入 Manifest。

本轮没有新增数据库表或迁移；产品专属配置和 payload 使用已存在的 JSON/JSONL 扩展点，避免重复存储。若后续需要查询型评测样本索引，再单独设计迁移。

## 验收条件

1. 训练授权才能构建预训练和 SFT；RAG/evaluation 用途独立门控。
2. 三类产品输出不同 Schema 的真实 JSONL，Manifest 哈希和对象内容一致。
3. RAG chunk size/overlap 改变会产生不同候选，保存 tokenizer/单位/定位。
4. 评测缺问题、参考答案或 evidence 时不形成可发布候选；重复题被排除。
5. 配置/候选/授权变化使旧快照发布失败；重复发布只返回同一版本；对象不可覆盖。
6. P0-C～F、P1-A、OpenAPI、迁移、静态检查和真实 Docker E2E 回归通过。

## 不在范围

在线 RAG、向量库、Rerank、模型效果评测、DPO、Parquet/Arrow、正式 OIDC 和生产部署不在 P1-B。
