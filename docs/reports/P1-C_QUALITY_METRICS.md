# P1-C 质量指标口径与真实样例

本报告对应质量评估报告版本 `p1c.v2`。指标由 `apps/api/src/corpusflow/services/quality_governance.py` 对 PostgreSQL 中的 Asset、DocumentVersion、Segment、CandidateSample、Review、授权记录和已发布 Manifest 计算；没有可靠参考标注的指标返回 `NOT_EVALUATED`，不会被折算成满分。

## 指标口径

| 类别 | metric_id 示例 | 分子/分母 | 单位/方向 |
|---|---|---|---|
| Schema | `schema.validity` | 通过产品 Schema 的样本 / 全部样本 | ratio / higher |
| 证据 | `evidence.completeness` | 具备完整 Segment→DocumentVersion→Asset→Source 链的样本 / 全部样本 | ratio / higher |
| 审核 | `review.approval_rate` | 有最新 approved 审核的样本 / 全部样本 | ratio / higher |
| 内容 | `sample.non_empty_rate`、`sample.duplicate_rate` | 非空样本 / 全部样本；重复内容超出首个出现次数 / 全部样本 | ratio / higher、lower |
| 片段 | `segment.empty_rate`、`segment.location_coverage`、`segment.source_completeness` | 对应异常或具备定位/来源链的 Segment / 证据 Segment | ratio / lower、higher |
| 文档 | `document.metadata_completeness`、`document.parsable_rate`、`document.abnormal_character_rate`、`document.html_noise_rate` | 按文档解析结果和元数据计算 | ratio / higher 或 lower |
| 评测 | `evaluation.leakage_rate` | 与训练样本稳定内容标识相交的评测样本 / 评测样本 | ratio / lower |
| 产品 | `sample.token_count` | 产品内容的 whitespace tokenizer token 总数 | tokens / descriptive |

每条结果同时保存 `metric_version`、计算方法、scope、`numerator`、`denominator`、阈值、方向、样本数、`rule_version_id`、计算时间和 evidence 引用。授权和来源质量是独立 gate，不参与质量指标抵消。

## 本地真实样例

`scripts/verify_p1c_quality.py` 在隔离 Docker PostgreSQL/Redis/MinIO 上创建 3 份真实 HTML，交给 Worker 解析，再分别发布 SFT、Pretrain、RAG、Evaluation。最近一次证据文件为 `.local/p1c/evidence.json`，包含四个版本的 Manifest 和对象内容 SHA-256。

代表性 Pretrain 评估（1 个样本、20 tokens，tokenizer `builtin-whitespace-1`）：

- `schema.validity`: `1/1 = 1.0`, PASS
- `evidence.completeness`: `1/1 = 1.0`, PASS
- `review.approval_rate`: `1/1 = 1.0`, PASS
- `sample.duplicate_rate`: `0/1 = 0.0`, MEASURED
- `segment.location_coverage`: `1/1 = 1.0`, MEASURED
- `document.metadata_completeness`: `1/3 = 0.3333`（fixture 元数据只登记了部分字段）
- 无可信公式、表格、OCR、领域相关性标注，相关指标为 `NOT_EVALUATED`。

同一证据脚本撤销一份授权后重新评估，独立授权 gate 变为 FAIL；修改规则版本并提高元数据阈值后生成新 EvaluationRun，旧发布版本的报告 SHA-256 未变化。评估配置使用幂等键重复提交时返回原 EvaluationRun。

## 覆盖与配比口径

覆盖接口的分母是筛选后的去重 Asset ID 数。多标签领域另外输出标签出现次数和去重资源数。最近样例为 3 个 HTML Asset：`cryptography/hash` 出现 6 次但仅对应 3 个资源，`cryptography/signature` 出现 3 次且对应 3 个资源；`knowledge_coverage` 为 `NOT_EVALUATED`，因为没有可信的目标领域全集。

配比接口分别按样本数和 token 数给出 source/domain/document_type/year/split 的 counts、denominator 和 ratios；RAG 不强制套用 SFT 的 train/validation/test 比例。
