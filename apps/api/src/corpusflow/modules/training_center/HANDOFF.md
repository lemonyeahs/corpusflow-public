# Agent 2 → Agent 1/3/4 接入说明

基线 `acb7ce0fa31befaa203bf1213ad3eebbc4afaa06`，Agent 2 分支 `feat/tc-catalog-datasets`。本文是模块边界说明，不是新共享协议。共享快照接口仍在开发，用户已确认尚无后续提交。

## Agent 1：快照注入与接口契约

现有目录 HTTP 授权入口每次验证 active Membership，包括缓存命中、详情和下载。数据库适配器只读取授权 workspace 的实体，不自行创建空间、修改记录或执行迁移。

`workspace.WorkspaceCatalogProvider` 提供以下 Python 接入点：

```python
def load(
    workspace: str,
    revision: str | None,
    session: Session,
    max_records: int = 100_000,
    max_bytes: int = 100 * 1024 * 1024,
) -> CatalogSnapshot: ...
```

Agent 1 的实现可以通过 `app.state.training_center_workspace` 注入，或通过 FastAPI dependency override 替换 `api.v1.training_center.workspace_store`。调用方仍先授权；provider 应返回同一 scope 下的不可变内容副本，约束最大记录数/字节数、过期和空间隔离，且复用 Agent 1 最终确定的共享 revision。已有契约测试验证 dependency override 可替换实现且不改变 wire scope；该测试**不代表统一快照服务已接通**。

目前默认仍是前轮的 `WorkspaceSnapshots`（固定900秒、每空间10份、不续期），与图模块内部 `GraphSnapshots` 不互认。请交付共享 provider 的调用签名/提交和应用注入位置，再由 Agent 2 适配。多进程共享缓存和跨模块同 revision 读取尚未验收。当前页面的 workspace 血缘链接省略目录 revision，使图建立独立快照；此时不能保证目录与图代表同一时点。

本轮增量：

| 接口 | 参数及响应 |
|---|---|
| `GET /api/v1/training-center/datasets/{dataset_id}/samples/{sample_id}` | catalog/revision、必填 version；复用 SamplesResponse：items 恰好一项、total_count=1、offset=0、limit=1。无此样本或不属于指定版本404；无需传列表 q/split/offset |
| `GET /api/v1/training-center/datasets/{dataset_id}/export` | catalog/revision、必填 version、split、q、export_format=jsonl/markdown/csv/txt；所有匹配结果、稳定 sequence/id 顺序；offset/limit 返回422；UTF-8二进制下载 |

未改共享 DTO。导出暂使用共享 ExportQuery 依赖加独立 Query(q)；请 Agent 1 将可空字符串 q 纳入 Python/TypeScript ExportQuery、设计 OpenAPI 和共享样例。之后可恢复模型整体 Query 绑定，保持未知参数拒绝行为。详情暂复用已有 SamplesResponse，若希望单独 DetailResponse，请由 Agent 1 统一定义再协调接入。

实际 `create_app().openapi()` 与基线共享快照的差异已计算到 [openapi_followup_delta.json](contract_examples/openapi_followup_delta.json)：只新增上述两条路径，无响应 schema 变更。这是评审材料，不会被生产服务加载，也没有覆盖共享 `docs/api/openapi.json`。请 Agent 1 更新该快照及设计契约；`tests/contract/test_openapi.py::test_schema_snapshot` 当前因此失败。

统计口径待确认：workspace 片段数按每份 Document 最新 DocumentVersion 的实际 Segment；样本证据允许引用历史片段。文件按 Asset，训练记录按已发布版本中关联的 CandidateSample（DPO每对一项）；同一候选被多个版本使用时每个版本分别计数。Tokens 无确定分词器时为 null。列表与文件统计使用相同文件过滤范围；数据集概览是版本总体，样本 total_count 是 q/split 后总体，页面明确标注版本总量。

## Agent 1/4：稳定关联读取

首先取得**已授权** `CatalogSnapshot`。generated 使用现有 `GeneratedCatalog.load(workspace, revision)`，不直接重新解析磁盘；workspace 从同一 provider 取得，不能新建快照后混接旧响应。

```python
from corpusflow.modules.training_center.relations import CatalogRelations

relations = CatalogRelations(snapshot)
files = relations.source_files(source_id)
file_links = relations.file(file_id)
version = relations.version(version_id)
sample_links = relations.sample(dataset_id, version.version, sample_id)
```

| 读取结果 | 关联及含义 |
|---|---|
| `source_files(source_id)` | 按 filename/id 排序的 FileSummary 元组；校验来源存在 |
| `file(file_id).versions` | 文件 dataset_refs 的 type=dataset_version、id=DatasetSummary.version_id；返回完整版本摘要，含 dataset id 与 version，避免把版本ID误作数据集ID |
| `file(file_id).latest_processing_run` | 文件最新真实 PipelineRun，仅表示文件当前处理概况；无则 None |
| `sample(...).files` | workspace 按 CandidateSample.evidence→Segment→DocumentVersion→Document→Asset；generated 按 source_refs 与版本成员关系，返回有序文件元组 |
| `sample(...).file_basis` | workspace 为 segment_evidence，generated 为 source_association；后者不能画成真实解析执行证据 |
| `sample(...).processing_runs` | 只纳入证据 DocumentVersion.run_id 对应、同空间且 asset_id 匹配的真实 PipelineRun；不以最新运行替代历史生产运行；缺失为空 |
| `sample(...).version` | 此样本所属的明确版本摘要；相同样本ID可能被不同版本使用，必须传 dataset_id+version |

generated 的 source/文件/样本/版本 IDs 全部沿用生成器及 manifest；没有 segment/operator_run/processing_run 就不产生引用。新的 facade 不查询数据库、不生成图节点ID、不执行处理；图规范化仍归 Agent 4。文件和样本不存在时明确404。工作空间关联和历史生产运行区别有隔离数据库测试，generated 有完整遍历测试。

## Agent 3：已接依赖与待补内容

导出直接调用 `services.processing_exports.serialize_records(records, kind, format)`，Agent 2 只处理版本/成员/实时 training LicenseGrant 授权、记录/字节上限、临时文件及审计。不维护第二套格式实现。CPT/SFT/DPO × JSONL/Markdown/CSV/TXT 的真实序列化单测通过；中文、引号、换行、来源引用及SFT顺序有断言。

workspace manifest 读取 DatasetVersion.manifest_storage_key，校验 manifest_sha256；对象存储不可用503，内容失配409。请提供隔离环境可读取的真实发布manifest及授权版本用于端到端联调。模型/迁移本轮无新请求。

文件/步骤对照还缺可靠持久化记录映射，当前 comparison 返回404 COMPARISON_NOT_AVAILABLE；处理摘要路由注册及 operator/记录映射由 Agent 1/3/4 协调。上述 PipelineRun 引用可用于导航，但不等于处理详情或清洗前后对照已经实现。

## 后续联合验收

共享快照实现到位后，验证首页→文件台→版本→图使用同一 revision、过期整体刷新、多进程缓存和跨空间隔离。真实隔离 PostgreSQL/S3/Worker 环境再验证旧 CPT/SFT/DPO 构建、审核、发布、manifest 和完整下载。浏览器当前测试使用 HTTP 拦截，后端契约测试使用真实应用路由及隔离 SQLite；两者不等于浏览器连接真实服务的验收，也不能替代 Agent 4 或人工独立复核。
