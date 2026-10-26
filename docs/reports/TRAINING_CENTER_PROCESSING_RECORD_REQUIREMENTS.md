# 训练数据中心处理执行记录需求（Agent 3 首轮）

本文记录当前实现与 Contract V1 的核对结果，作为 C→A/D 的交接材料。本文不修改共享契约，也不把静态原型中的数字当作真实处理结果。

## 当前调用链

1. `execute_pipeline_run` 在 `apps/api/src/corpusflow/worker/tasks.py` 读取 `Asset`、`AssetBlob` 和对象存储内容。
2. Worker 根据资产格式选择 `PDFParserAdapter`、`HTMLParserAdapter` 或 `TextParserAdapter`；OCR/Layout 仍由显式 `parser` 配置覆盖 PDF 入口。
3. 解析结果写入 `document.md`、`document.json` 两个 `Artifact`，并创建 `DocumentVersion`、`Segment` 及原始文件到版本/片段的 `LineageEdge`。
4. `_run_processing_chain` 在 `apps/api/src/corpusflow/services/processing_pipeline.py` 中按配置执行 `builtin.clean`、`builtin.deduplicate`、`builtin.quality`，每个算子创建或复用一个 `NodeRun`，并将结果写入派生版本和 JSON Artifact。
5. `ExecutionLog` 记录解析、算子成功或失败消息；Celery 重试以 `NodeRun.attempt_no` 和 `Artifact` 的 attempt 路径区分。

## 处理计数核对

| 口径 | 当前实现 | Contract V1 | 结论 |
|---|---|---|---|
| 解析输入 | `NodeRun.input_count = 1`，单位隐含为文件 | 解析允许 file→segment，不套用记录守恒 | 可用，但应显式记录 input unit |
| 解析输出 | `len(ParseResult.sections)` | 文件/片段单位需区分 | 当前按 section 计数，建议明确为 segment |
| 算子输入/输出 | `NodeRun.input_count/output_count` | `ProcessingStepSummary` 要求 nullable count | 已有基础字段，缺少单位字段 |
| 成功/保留 | `output_count`，Pipeline 成功由 `run.status` 表达 | `status=succeeded/partial/failed` | 成功可表达，部分成功尚未由代码计算 |
| 过滤 | `NodeRun.filtered_count`、`ProcessingResult.filtered_count` | `filtered_count` 是独立计数，不能重复加到 modified | 已实现 |
| 修改 | 仅写入算子 metrics，未落 NodeRun | 要求 `modified_count` | 缺失 |
| 失败 | `failure_code`、`PipelineRun.error_code`、错误日志 | 要求 `failed_count` 与失败原因 | 原因已有，失败数量缺失 |
| 跳过 | 无统一字段；已成功 NodeRun 会被跳过复用 | 契约业务口径要求跳过可区分 | 缺失，建议由执行摘要层计算/补字段 |
| 重试 | `attempt_no`，失败尝试独立 Artifact | 重试不能重复累计输出 | 机制已有，汇总 API 必须只选最终产出 attempt |
| Pipeline 汇总 | `PipelineRun.status`，无持久化总计 | 需 ordered steps、totals、refs | 缺少摘要序列化器/API |

当前可采用的统计规则：一个顶层文件作为解析输入；解析输出按实际生成的 segment 数统计；清洗算子按同一批 segment 统计，已结束步骤满足 `input = output + filtered + failed`，`modified` 是 output 的子集；失败重试按 attempt 分开记录，Pipeline 汇总只汇总最终成功/部分成功 attempt。空文本解析为 `EMPTY_DOCUMENT`，输入计数为 1、输出为 0 的失败执行；非法编码/二进制输入同样保留失败原因，不伪造输出。

## 清洗执行记录字段需求

| 字段 | 业务含义 | 现有实现 | Contract V1 是否定义 | 建议 | 负责人 |
|---|---|---|---|---|---|
| `run_id` | 一次 Pipeline 执行标识 | `PipelineRun.id` / `NodeRun.run_id` | 是 | 保持现有 ID | C |
| `node_run_id` | 一次算子实际执行（含 attempt） | `NodeRun.id`、`attempt_no` | 以 `operator_run` ObjectRef 表达 | 汇总/API 输出稳定引用 | C + D |
| `attempt` | 重试序号 | `NodeRun.attempt_no` | `ProcessingStepSummary.attempt` | 保持每次尝试独立 | C |
| `operator_key/version` | 算子身份与可复现版本 | 两字段已有 | 是 | 不仅保存展示名称 | C |
| `config_hash` | 参数配置内容哈希 | 只有 `config_snapshot`，Pipeline 有 `snapshot_hash` | 是 | 在 NodeRun/摘要中计算并返回 | C |
| `input_refs/output_refs` | 输入与输出产物、片段引用 | `Artifact`、LineageEdge 已有，NodeRun 未关联 | 是 | 摘要层返回 ObjectRef；按最终 attempt 过滤 | C + D |
| `input_count/output_count` | 当前步骤输入/输出数量 | NodeRun 已有，固定整数默认 0 | 是 | 未结束时 API 映射为 `null`，并带 unit | C |
| `input_unit/output_unit` | file/record/segment 计数单位 | 未实现 | 是 | 解析 file→segment，清洗 segment→segment | C |
| `modified_count` | 输出中发生文本修改的数量 | 仅 metrics 中可选 | 是 | 增加持久化字段或由不可变执行摘要保存 | C，需 A 评审 |
| `filtered_count` | 被算子过滤的数量 | NodeRun 已有 | 是 | 保持守恒口径 | C |
| `failed_count` | 处理失败数量 | 仅 failure_code，无数量 | 是 | 增加字段；单文件解析失败至少记录 1 | C，需 A 评审 |
| `status` | queued/running/succeeded/partial/failed | Pipeline/NodeRun 已有但值域未统一 | 是 | 对外严格映射 Contract V1 枚举 | C + A |
| `started_at/completed_at` | 执行时间边界 | Pipeline 有时间，NodeRun 只有 duration | 是 | NodeRun 增加时间或摘要计算 | C，需 A 评审 |
| `log_ref` / execution log | 可追踪执行日志 | `NodeRun.log_ref`、`ExecutionLog` 已有 | 是（日志语义） | 错误消息保留 code 与 attempt | C |
| `failure_code/reason` | 机器码与可读失败原因 | `failure_code`、日志已有 | 是（失败原因） | API 同时返回 code/message，避免泄露原文 | C |
| `record_id` 对比引用 | 清洗前后同一记录关联 | Segment/LineageEdge 已有，比较 API 未实现 | 是 | 只按真实 ID 对齐，不按索引猜配 | C + F/E |
| `source_refs/lineage` | 原始文件到派生片段血缘 | LineageEdge 已有多条关系 | 是 | 由 D 统一方向与节点 ID，C 提供执行证据 | C + D |

## 需要协作的变更请求

- **给 Agent 1**：共享 DTO/API 需要在下一版明确 `input_unit`、`output_unit`、`modified_count`、`failed_count`、`started_at`、`completed_at` 和 `input_refs/output_refs` 的序列化位置；建议以兼容新增字段更新契约，不在本分支直接改共享契约或入口注册。
- **给 Agent 4**：算子节点 ID 使用实际 `NodeRun.id`（同一 `run_id` 下由 `attempt_no` 区分）；边从上游 ObjectRef 指向下游 ObjectRef。重试失败 attempt 不连接为最终产物，重复执行通过 `(run_id, node_run_id, output_ref)` 去重。
- **给 Agent 2**：导出选择版本和记录由 B 负责，调用 C 的通用序列化器；处理摘要中的 `source_refs`、`segment_refs` 必须原样保留。
