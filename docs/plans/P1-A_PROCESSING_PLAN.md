# CorpusFlow P1-A 专业文档解析与数据处理计划

日期：2026-10-24
基线：`b1c54f1 feat: harden P0 system acceptance`
范围：专业 PDF/HTML 解析增强、清洗/去重/质量算子、版本化处理链、评测集和真实 Worker/UI 验收；不进入 P1-B～P1-D。

## 现状与缺口

P0 已有 `PDFParserAdapter`、`HTMLParserAdapter`、单一 parse NodeRun、DocumentVersion/Segment、Artifact 和真实 Celery/MinIO 链路。当前 PDF 解析以 pypdf 文本层为主，Segment 只有文本和哈希；Pipeline DAG 只保存默认 parse/quality 节点，NodeRun 没有算子版本、输入输出量和过滤统计；Web 处理页只能创建 Run、看日志和恢复。

P1-A 保留这些 P0 接口和状态机，增加可追溯的处理适配器边界和派生 DocumentVersion。外部组件不作为隐含成功路径。

## 任务清单

| 任务 | 优先级 | 依赖 | 变更 | 验收 |
|---|---|---|---|---|
| `TASK-CF-201` 解析器能力增强 | P1 | P0 解析器 | PDF 页/行定位、公式和表格 marker、HTML 结构元数据、9 份合成评测夹具 | 解析 benchmark；扫描/加密/损坏明确失败 |
| `TASK-CF-202` ProcessingAdapter/Operator Registry | P1 | P0 Pipeline | 内置 clean、exact deduplicate、quality；Data-Juicer/docreader 明确未配置适配器 | 单元、契约和外部 adapter NOT RUN |
| `TASK-CF-203` 版本化算子链 | P1 | 201/202、0008 | parse → clean → deduplicate → quality；NodeRun 指标、对象产物、derived DocumentVersion 和 LineageEdge | 真实 Worker E2E；重复执行不覆盖旧产物 |
| `TASK-CF-204` 真实处理 API/Web | P1 | 203 | 算子注册、Run 节点、Artifact API；处理页显示配置、节点指标、失败和产物 | Playwright P1-A |
| `TASK-CF-205` 评测与对比报告 | P1 | 201/202 | 可复现 benchmark、外部组件评估和限制 | `P1-A_PARSER_BENCHMARK.md`、验收报告 |

## 数据与 API

- `0008_p1a_processing` 新增 `operator_definitions`；扩展 `node_runs` 的 operator/config/count/duration/failure 字段；扩展 `document_versions` 的 parser/config/run/status；扩展 `segments` 的 location/token/section 字段。
- `GET /api/v1/processing/operators` 返回可用算子和未配置外部适配器。
- `GET /api/v1/pipeline-runs/{run_id}` 返回节点快照与统计。
- `GET /api/v1/pipeline-runs/{run_id}/artifacts` 返回不可变中间产物引用。
- 资产/DocumentVersion API 返回 parser、配置哈希、定位和 token 统计。

所有 Run 使用创建时的 `config_snapshot`；模板后续变更不修改历史 Run。算子输出写入 `artifacts/{run_id}/{node}/output.json`，派生版本只在实际内容改变时创建，旧版本和血缘保留。

## 外部组件决策

- WeKnora/docreader 当前公开协议是 gRPC `Read`/`ReadStream`，返回 Markdown、metadata 和可选 source blocks；扫描件 OCR/VLM 需要额外服务。仓库未配置 endpoint、proto client 或 OCR/VLM 依赖，因此本轮只实现 `DocReaderAdapter` 边界并标记 NOT RUN。
- Data-Juicer 当前以 recipe/CLI/Python pipeline 运行，包含清洗、过滤和多种 document deduplicator；仓库未锁定其 Python/Ray/模型依赖，因此本轮使用本地等价算子，并通过 `DataJuicerAdapter` 在未配置时返回 `ADAPTER_NOT_CONFIGURED`。
- 外部组件接入前必须锁定 commit/tag、许可证、资源预算、输入输出契约和回归样本。不得把本地算子结果标记为 Data-Juicer 或 docreader 结果。

## 测试计划

- unit：Parser 错误、清洗/去重/质量统计、外部 adapter 不能伪造成功。
- integration：0008 migration、真实 MinIO 中间产物、Worker 版本化链和血缘。
- contract：OpenAPI 与 DTO；算子 schema 和错误码。
- e2e：真实 Docker 上传 PDF → Run → 节点 → Artifact → DocumentVersion/Segment；损坏/扫描/加密失败。
- benchmark：9 份合成 fixture，记录文本 marker 完整率、章节、公式、表格、定位、耗时和失败码。

## 不在本轮

正式 OCR/VLM、版面级多栏重排、复杂表格结构恢复、Data-Juicer/WeKnora 生产部署、分布式算子调度、Parquet、语义去重和 P1-B 之后的 RAG/评测产品均不在范围。
