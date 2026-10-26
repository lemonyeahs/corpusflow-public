# Training Center Agent 4 验收清单（首轮）

状态基线：`263821e`（`public/main`），worktree：`feat/tc-lineage-validation`。
本轮只验证可独立执行的图遍历语义和现状契约；没有把静态 fixture 当作真实数据库血缘验收。

## 血缘现状

当前系统已经有独立的 `lineage_edges` 表（`apps/api/src/corpusflow/db/models.py:590`），字段为
`workspace_id/from_type/from_id/to_type/to_id/relation`，但没有外键、唯一约束、深度或执行版本字段。
现有写入点包括：

- 资产接入：`services/acquisition.py` 将 `Source`、`DiscoveryCandidate`、`IngestPlan` 指向 `Asset`。
- 解析 Worker：`worker/tasks.py` 写入 `Asset -> DocumentVersion`、`Asset -> PipelineRun`、
  `PipelineRun -> DocumentVersion`、`DocumentVersion -> Segment`，重试时写入
  `Segment -> Segment (reprocessed_equivalent)`。
- 清洗：`services/processing_pipeline.py` 写入版本转换、输入版本与片段、片段与派生版本。
- 数据集物化：`services/dataset_materializer.py` 写入 `CandidateSample -> DatasetVersion`、
  `Segment -> DatasetVersion`、`Source -> DatasetVersion`。

已有 `GET /api/v1/lineage/{object_type}/{object_id}` 只返回同一对象的一跳相邻边；
`GET /api/v1/assets/{asset_id}/lineage-view` 返回资产的解析版本和存储产物摘要。当前没有 V1
要求的 `/api/v1/lineage/graph` 多跳接口，也没有统一的节点详情、方向、深度或节点规模边界。

## Contract V1 对照与建议

| 项目 | V1 已明确 | 当前实现 | 首轮结论 |
|---|---|---|---|
| 起点 | `catalog/root_type/root_id` | 旧接口只有 `object_type/object_id` | 新图接口需采用 V1 参数 |
| 方向 | `both/upstream/downstream` | 旧接口固定一跳双向 | 适配层保持存储边方向，查询方向只控制遍历 |
| 深度/规模 | 默认 6；上限 12/500 | 无参数 | 图服务已实现校验和截断语义 |
| 节点 | `id/ref/kind/label/description/status/metrics/detail` | 旧接口没有节点 | A/D 需共同落地 DTO；本轮 fixture 保留 kind/id/label/status/detail |
| 边 | `id/source/target/relation` | `LineageEdge` 无 id/唯一约束 | 适配层按五元组去重；API 需生成稳定边 id |
| 关系 | 英文代码，前端中文映射 | 实际有 `parsed_to/contains/processed_by/produced` 等 | 需要 D 维护规范化映射表，不在前端猜方向 |
| 缺失/悬空 | 不泄露、所有返回边端点必须在 nodes | 旧查询直接返回行 | 新接口应过滤不可见端点并区分 404/空图 |
| 多路径/环路 | 未重复节点，明确截断 | 无多跳能力 | fixture 覆盖去重、汇合和环路保护 |
| 产物关联 | 依赖 C 的真实执行记录 | `Artifact.run_id` 与 `DocumentVersion.run_id/artifact_id` 已有 | NodeRun 目前无输入/输出引用，需 C 补字段或适配 JSON |

Contract 文本本身有一处重复的 `description` 字段示例；属于 A 统一契约整理项，本轮未修改共享文件。

## 可重放验收场景

状态只能在实际执行后填写 `PASS`。当前 fixture 结果来自 `python scripts/verify_training_center.py`；
真实 API 场景统一为 `NOT RUN`，原因写在每项前置依赖中。

| 编号 | 验收目标与操作 | 预期节点/关系 | 验证方法 | 前置依赖 | 状态 |
|---|---|---|---|---|---|
| A | 从 `Asset` 查询下游，追到解析版本和处理产物 | Asset → PipelineRun → DocumentVersion；关系 `processed_by/produced` | 图响应节点、边集合 | D 路由、C 真实 run | NOT RUN |
| B | 从 `DatasetVersion` 查询上游来源 | DatasetVersion ← CandidateSample/Segment ← DocumentVersion ← PipelineRun ← Asset/Source | 反向遍历但边仍 source→target | B 数据集来源、C 产物 | NOT RUN |
| C | 2、3、6 跳查询 | 节点按深度增加，达到边界 `truncated=true` | 精确集合比对 | D 深度参数 | NOT RUN |
| D | 清洗/解析执行追踪 | run、node/operator、输入输出 artifact 可关联 | run_id、attempt、artifact 引用一致 | C 提供 NodeRun 输入输出 refs | BLOCKED：当前 NodeRun 没有引用字段 |
| E | 悬空边、错误节点、重复路径和环路 | 悬空边不出现在响应；节点/边去重；环路终止 | fixture 单元测试 | 图适配层 | PASS（fixture） |
| F | 前后端一致性 | 页面节点/边与真实 API 完全一致 | UI 响应快照与 API 集合比对 | A 注册路由、D 页面 | NOT RUN |
| G | 分叉与汇合 | 两个 Segment 汇合到同一 DatasetVersion 只保留一个节点 | 节点 ID 集合与五元组边集合 | D 图接口 | PASS（fixture） |
| H | 参数/规模边界 | 非法 direction/depth/nodes 返回 422；规模截断有原因 | 单元测试 + HTTP 合约测试 | D 路由 | PASS（服务层）；NOT RUN（HTTP） |

## 执行命令与结果

```bash
python scripts/verify_training_center.py
uv run pytest tests/unit/test_lineage_graph.py
uv run ruff check apps/api/src/corpusflow/modules/lineage_graph tests/unit/test_lineage_graph.py scripts/verify_training_center.py
```

本轮真实 API、浏览器截图和跨页面数据一致性均为 `NOT RUN`，因为共享图路由尚未注册，且没有
可复用的认证工作空间 fixture。fixture 只证明遍历算法的输入/输出集合和边方向。

## 跨 Agent 变更请求

### Agent 1（中阻塞）

- 背景：V1 图响应需要统一 DTO、`/api/v1/lineage/graph` 注册和 Hash 路由接入。
- 缺口：当前没有 `LineageGraph` 的 Pydantic/TypeScript 共享类型，旧路由不支持 catalog、方向、深度。
- 建议：按 V1 响应新增独立 router，由 A 在主路由注册；边始终 source→target；把 `catalog` 纳入对象引用和授权检查。
- 负责：Agent 1 负责公共契约/注册，Agent 4 提供服务层和 fixture。
- 阻塞：没有该接口无法执行 HTTP/前端验收。

### Agent 2（中阻塞）

- 背景：数据集反向追溯必须从生成或 workspace 数据集找到来源文件和版本。
- 缺口：需确认 generated manifest 的 `lineage-edges.jsonl`、`source_refs`、`segment_refs` 是否稳定；workspace 数据集需提供 DatasetVersion/CandidateSample/Segment 关联。
- 建议：提供同一 revision 的节点/边适配器和 manifest provenance；未执行的 processing-runs 保持为空，不伪造 operator 节点。
- 负责：Agent 2 提供目录适配器和来源标识，Agent 4 负责遍历。
- 阻塞：没有来源引用只能验收数据集节点本身，不能验收完整回溯。

### Agent 3（高阻塞）

- 背景：解析、清洗和重试是血缘图中最关键的中间节点。
- 缺口：当前 `NodeRun` 只有计数、状态、operator/version/config，没有输入输出对象引用；`Artifact` 只有 run_id，处理版本通过 `DocumentVersion.run_id/artifact_id` 间接关联。
- 建议：由 Agent 3 在自己的模型/迁移范围内定义 input_refs/output_refs（或稳定 JSON 记录）和 attempt 语义；失败/重试只暴露真实执行记录；明确谁写入 `operator_run` 边。
- 负责：Agent 3 写入执行记录，Agent 4 适配查询和验证。
- 阻塞：场景 D 及真实多跳 operator 图无法通过。
