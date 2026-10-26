# Training Center Agent 4 验收清单（首轮）

> 本文记录 Agent 4 在 M1 基线上的验收范围。workspace 图冻结快照、generated 发布目录读取和处理节点适配已纳入定向验证；这些验证不代替真实 Worker 多跳链路和浏览器联调。

状态基线：`acb7ce0`（`feat/tc-lineage-validation`），worktree：`feat/tc-lineage-validation`。
M1 已接入 workspace/generated 图查询适配器和独立血缘页面；本报告仍不把静态 fixture 当作真实数据库血缘验收。

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
`GET /api/v1/assets/{asset_id}/lineage-view` 返回资产的解析版本和存储产物摘要。M1 新增
`GET /api/v1/lineage/graph`，workspace 目录读取 `lineage_edges`，支持方向、深度、节点规模限制、
稳定节点/边 ID、悬空端点过滤和截断原因；generated 目录复用 Agent 2 的 `GeneratedCatalog` 固定 revision，
只投影真实 source/file/sample/dataset_version 引用，没有处理记录时不生成 operator 节点。

## Contract V1 对照与建议

| 项目 | V1 已明确 | 当前实现 | 首轮结论 |
|---|---|---|---|
| 起点 | `catalog/root_type/root_id` | 新接口已采用 V1 参数；旧接口保持不变 | workspace/generated 均已接入 |
| 方向 | `both/upstream/downstream` | 旧接口固定一跳双向 | 适配层保持存储边方向，查询方向只控制遍历 |
| 深度/规模 | 默认 6；上限 12/500 | API 支持 `max_depth`/`max_nodes`，并返回截断原因 | 图服务已实现校验和截断语义 |
| 节点 | `id/ref/kind/label/description/status/metrics/detail` | workspace/generated 均生成完整 DTO；workspace operator 节点带 run/step/attempt 详情 | 处理引用以 C 的 summary adapter 为来源 |
| 边 | `id/source/target/relation` | API 按五元组生成稳定 id | 适配层按五元组去重 |
| 关系 | 英文代码，前端中文映射 | API 规范化关系代码；页面显示中文关系 | 未知关系统一为 `derived_from/关联` |
| 缺失/悬空 | 不泄露、所有返回边端点必须在 nodes | 新接口过滤悬空端点，根节点缺失返回 404 | 旧查询保留历史行为 |
| 多路径/环路 | 未重复节点，明确截断 | 无多跳能力 | fixture 覆盖去重、汇合和环路保护 |
| 产物关联 | 依赖 C 的真实执行记录 | workspace 读取 C 的 `build_processing_summary` 输入/输出引用；generated 无执行历史 | 仍需 C/人工独立复核真实 Worker 端到端证据 |

Contract 文本本身有一处重复的 `description` 字段示例；属于 A 统一契约整理项，本轮未修改共享文件。

## 可重放验收场景

状态只能在实际执行后填写 `PASS`。当前 fixture 结果来自 `python scripts/verify_training_center.py`；真实 Worker 和浏览器场景仍按实际执行结果记录，原因写在每项前置依赖中。

| 编号 | 验收目标与操作 | 预期节点/关系 | 验证方法 | 前置依赖 | 状态 |
|---|---|---|---|---|---|
| A | 从 `Asset` 查询下游，追到解析版本和处理产物 | Asset → PipelineRun → DocumentVersion；关系 `processed_by/produced` | 图响应节点、边集合 | C 真实 run、认证 workspace | NOT RUN |
| B | 从 generated `DatasetVersion` 查询上游来源 | DatasetVersion ← CandidateSample/File ← Source | 固定 revision 图响应集合 | 已发布 generated catalog | PASS（投影/发布目录 HTTP/单测） |
| C | 2、3、6 跳查询 | 节点按深度增加，达到边界 `truncated=true` | 精确集合比对 | D 深度参数 | NOT RUN |
| D | 清洗/解析执行追踪 | run、node/operator、输入输出引用可关联 | run_id、attempt、input_refs/output_refs 一致 | C summary adapter、真实 Worker | PASS（隔离 SQLite summary adapter）；真实 Worker input/output refs NOT RUN |
| E | 悬空边、错误节点、重复路径和环路 | 悬空边不出现在响应；节点/边去重；环路终止 | fixture 单元测试 | 图适配层 | PASS（fixture） |
| F | 前后端一致性 | 页面节点/边与真实 API 完全一致 | UI 图、目录切换和节点深链 | 认证 workspace、浏览器回归 | PASS（真实浏览器图/目录切换）；节点深链目标由 mock 浏览器契约覆盖；完整 API 节点边集合比对 NOT RUN |
| G | 分叉与汇合 | 两个 Segment 汇合到同一 DatasetVersion 只保留一个节点 | 节点 ID 集合与五元组边集合 | D 图接口 | PASS（fixture） |
| H | 参数/规模边界 | 非法 direction/depth/nodes 返回 422；规模截断有原因 | 单元测试 + HTTP 合约测试 | D 路由 | PASS（服务层/HTTP） |

## 执行命令与结果

```bash
PYTHONPATH=apps/api/src uv run python scripts/verify_training_center.py
uv run pytest -m 'not integration' -q
uv run ruff check apps/api/src/corpusflow/api/v1/lineage_graph.py tests/unit/test_lineage_graph_api.py scripts/verify_training_center.py
PYTHONPATH=apps/api/src uv run python scripts/export_training_center_contract.py --check
PYTHONPATH=apps/api/src uv run python scripts/verify_training_center_m0.py --catalog
```

本轮 workspace/generated API 适配器、处理节点详情和页面代码已完成定向验证；真实隔离 PostgreSQL/API 验收通过 67 项，
真实浏览器验收 7 项全部通过，覆盖目录读取、授权、快照、workspace/generated 图和目录切换；节点深链由独立 mock 浏览器契约另行覆盖。完整跨页面数据一致性和真实 Worker
产生的多跳边仍为 `NOT RUN`，因为本轮没有启动 Worker/Redis/MinIO。

结果：后端 `361 passed, 15 deselected`，图路由单测及发布目录 HTTP 测试 `16 passed`，隔离真实 HTTP `67 checks`、真实浏览器 `7 passed`，Ruff、mypy、契约导出检查均通过；
前端 `typecheck`、`lint`、`build` 均通过。构建仅报告已有的大 chunk warning。

最新隔离报告：`.local/cf-m1-04647a337779/result.json`，其中 `catalog-http.json` 为 67 项请求检查，
`live-browser.log` 为 7 项真实浏览器检查。

部署限制：workspace 冻结快照当前保存在单进程内存，900 秒过期且读取不续期，每个 workspace 最多保留 10 份；
重启或多进程访问需要共享不可变快照存储或粘性路由。本轮未声称已有共享快照存储，也未进行多进程验证。

跳转边界：文件节点可跳转到带 `catalog/revision/file_id` 的数据页；样本和数据集版本链接会保留
`dataset_id/version/sample_id`，但当前 `/datasets/{kind}` 仍由占位页承接；处理记录链接带 `run_id`，
处理中心是否按该参数定位具体记录仍待 Agent 3/页面线补齐。因此本轮只验收链接范围和作用域参数，
不把目标业务页渲染或处理记录定位计为已完成。

## 跨 Agent 变更请求

### Agent 1（中阻塞）

- 背景：V1 图响应需要统一 DTO、`/api/v1/lineage/graph` 注册和 Hash 路由接入。
- 当前：共享 DTO、主路由注册和页面入口已由 M0/M1 合并；本轮已接入生成目录读取。
- 需求：保留 generated catalog 的来源边和稳定 revision，未执行处理链不得生成 operator 节点。
- 负责：Agent 2 提供目录发布与授权 fixture，Agent 4 接入图查询。
- 阻塞：共享目录 fixture 尚未进入默认开发服务；本轮已用专用 PostgreSQL/API 临时目录完成真实 HTTP/浏览器验证。非空处理目录继续按 `ADAPTER_UNAVAILABLE` 失败。

### Agent 2（中阻塞）

- 背景：数据集反向追溯必须从生成或 workspace 数据集找到来源文件和版本。
- 缺口：需提供共享已发布 generated workspace 的浏览器复核；非空处理文件仍等待处理目录协议。
- 建议：继续使用 `GeneratedCatalog.load()` 和 `source_ref/dataset_refs/source_refs`，未执行的 processing-runs 保持为空。
- 负责：Agent 2 提供目录发布与授权 fixture，Agent 4 负责遍历。
- 阻塞：默认开发服务仍没有共享目录 fixture；专用发布目录 HTTP 和浏览器复核已通过。

### Agent 3（高阻塞）

- 背景：解析、清洗和重试是血缘图中最关键的中间节点。
- 缺口：当前 `NodeRun` 只有计数、状态、operator/version/config，没有输入输出对象引用；`Artifact` 只有 run_id，处理版本通过 `DocumentVersion.run_id/artifact_id` 间接关联。
- 建议：由 Agent 3 在自己的模型/迁移范围内定义 input_refs/output_refs（或稳定 JSON 记录）和 attempt 语义；失败/重试只暴露真实执行记录；明确谁写入 `operator_run` 边。
- 负责：Agent 3 写入执行记录，Agent 4 适配查询和验证。
- 阻塞：场景 D 及真实多跳 operator 图无法通过。
