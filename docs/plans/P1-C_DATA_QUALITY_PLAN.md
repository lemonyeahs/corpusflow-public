# CorpusFlow P1-C 数据质量治理计划

## 范围与基线

本阶段基于 P0-A～P0-I、P1-A 和 P1-B 已有的 `QualityIssue`、`Segment`、`DatasetBuild`、`CandidateSample`、`DatasetVersion`、Manifest、MinIO 与血缘能力，新增版本化质量规则、评估快照、覆盖/配比分析和不可变版本比较。P1-D 的在线 RAG、向量检索和模型效果评测不在范围内。

## 现状与缺口

- 已有质量问题和人工审核状态，但没有可配置的 QualityRuleSet/Version，也没有可追溯的指标结果快照。
- P1-A 算子能计算基础统计，但结果主要留在 NodeRun/日志，不能独立查询或与发布版本绑定。
- P1-B 已有四类产品的真实 JSONL、Manifest、授权门控和血缘；发布前没有统一的质量评估快照门控。
- Web 仅展示 QualityIssue，缺少指标、覆盖、配比和版本比较页面。

## 任务拆分

| 任务 | 优先级 | 结果 |
|---|---|---|
| TASK-CF-P1C-001 | P0 | QualityRuleSet/Version、EvaluationRun、MetricResult、Report、VersionComparison 模型和 `0009_p1c_quality_governance` 迁移 |
| TASK-CF-P1C-002 | P0 | 确定性质量指标计算、授权硬门控、NOT_EVALUATED 语义和不可变 JSON 报告 |
| TASK-CF-P1C-003 | P0 | 质量规则/评估/报告/覆盖/配比/版本比较 API，保持 workspace/RBAC/审计/错误码 |
| TASK-CF-P1C-004 | P0 | 发布前质量门控；失败评估阻断发布，历史发布版本不可修改 |
| TASK-CF-P1C-005 | P1 | React 质量中心展示规则、评估、指标、覆盖和版本比较 |
| TASK-CF-P1C-006 | P0 | 单元、迁移、真实 Docker/MinIO、API 和 Playwright 验收及交付报告 |

## 数据模型与口径

- 所有规则采用 `QualityRuleSet` + 不可变 `QualityRuleVersion.rules_json/config_hash`。评估保存规则快照，不回写历史报告。
- `QualityEvaluationRun` 记录目标（dataset_build 或 dataset_version）、产品类型、规则版本、状态、配置快照和运行时间。
- `QualityMetricResult` 记录 metric_id/version、分子/分母、单位、阈值、方向、样本范围、证据引用和 PASS/FAIL/NOT_EVALUATED。
- `DatasetQualityReport` 是绑定已发布版本的不可变 JSON 快照；重新评估创建新 run/report。
- 覆盖统计的分母明确为“workspace 已登记资源”，多标签同时输出标签出现次数与去重资源数，不宣称覆盖整个密码学领域。
- 授权是独立硬门控，不与质量分相互抵消；无可信标注的指标为 NOT_EVALUATED。
- 版本比较按稳定 sample_key、payload_hash、source_id 和内容哈希联合判断新增/删除/保留/变化；规则或 tokenizer 不同则质量指标标记不可直接比较。

## API 设计

- `GET /quality/rules`
- `POST /quality/evaluations`、`GET /quality/evaluations/{id}`
- `GET /quality/reports/{dataset_version_id}`
- `GET /quality/coverage`
- `GET /quality/ratios/{dataset_version_id}`
- `POST /quality/version-comparisons`、`GET /quality/version-comparisons/{id}`

所有接口从会话 workspace 过滤资源，记录审计事件，返回既有错误 DTO；发布使用最新 build 评估的硬门控结果。

## 实施顺序与验收

1. 写模型和迁移，验证 `0008 -> 0009 -> downgrade`。
2. 实现确定性评估、覆盖/配比/比较服务和 API。
3. 在发布事务前检查 build 的最新评估；失败或授权不通过返回稳定错误码。
4. 更新 OpenAPI、前端 API/types/质量页面。
5. 执行 pytest、ruff、mypy、迁移和真实 Docker/MinIO 验证；补充 P1-C 报告、指标样例和版本比较样例。

验收必须证明不同文档产生不同指标、规则变化生成新 run、历史快照不变、授权/质量失败阻断、四类产品分别生效、跨 workspace 拒绝、真实 Manifest/样本/报告一致。无法可靠判定的维度必须显示 NOT_EVALUATED。
