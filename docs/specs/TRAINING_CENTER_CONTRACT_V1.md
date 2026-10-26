# 训练数据中心共享契约 v1（M0 冻结基线）

配套：[并行开发任务书](../plans/TRAINING_CENTER_PARALLEL_PLAN.md)。

版本：`1.0.0`，统计口径版本：`1.0.0`。集成负责人根据 Agent 2/3/4 交付和独立复核冻结 M0 接口设计；不表示下面的新业务接口已经存在。后续破坏性修改需提升契约版本并同步所有调用方。

唯一类型来源是 `apps/api/src/corpusflow/contracts/training_center/models.py`。前端从 `src/contracts/training-center.ts` 导入自动生成的 wire DTO；禁止直接编辑 `.generated.ts`。统一样例为 `contracts/training-center/examples.json`。设计 OpenAPI 为 `docs/api/training-center.openapi.json`，路径按现状标记 planned/implemented；实际已注册路由仍以 `docs/api/openapi.json` 为准，implemented 不表示所有 catalog 均已实现。响应严格校验字段与语义，Query DTO 允许 FastAPI 解码 HTTP 字符串参数。

M2 的 workspace 快照共用、文件关联与处理路由注册条件见 [公共接入请求](../plans/TRAINING_CENTER_M2_INTEGRATION_REQUESTS.md)。这些是对冻结语义的实现要求，未新增 wire 字段。基线 acb7ce0 的 workspace 目录尚未实现，图使用独立快照，处理 router 尚未通过注册审查；三者不能互相回显 revision 来冒充统一快照。

## 1. 全局约定

- 业务 API 前缀 `/api/v1`，沿用现有 Bearer token、`X-Workspace-ID` 和错误包裹结构。
- 新页面默认目录是 `catalog=generated`；真实上传完成后的跳转显式使用 `catalog=workspace`。URL 与查询键保留目录选择，后端不可混合统计两个目录。
- `generated`：受当前工作空间授权约束的只读生成文件目录。`workspace`：现有真实资产/运行/训练数据，通过数据库适配器读取。两者都是正常 API 数据来源，开发请求拦截样例另有显式开关，不能混淆。
- `scope = {workspace_id, catalog, revision, as_of, metric_definition_version}`。generated revision 为 manifest 的内容版本，as_of 为其 generated_at；workspace revision 为后端分配的统计快照标识。保留策略见第 9 节。
- 列表默认 `offset=0, limit=20`，`limit` 上限 100；返回 `{scope, items, total_count, offset, limit}`，有稳定排序及 ID 二级排序。
- 日期使用 ISO 8601 UTC。趋势展示时区使用显式 `timezone`，默认 UTC，页面标明时区。
- 数量使用整数，比例使用 `[0,1]` 浮点值；小数转百分比由前端格式化。`null` 表示没有依据或没有统计，不可当成 0。
- 选中的 generated revision 在单次页面浏览中固定；更换版本后统计、分页、详情共同刷新。请求过期快照返回 `409 SNAPSHOT_EXPIRED`，前端刷新整体查询，不能拼接新旧版本。
- 所有数据集和对象 ID 按字符串处理。对象引用必须含 catalog、type、id，跨系统不能只凭同名 ID 认为是同一个对象。
- API enum 用英文，界面标签用中文。后端输出英文 relation code，D 维护统一中文映射。
- 未授权/不存在对象遵循项目既有错误策略，不泄露其他工作空间实体或文件路径。

## 2. 页面路由（A 注册，页面作者不改 App.tsx）

| URL | 页面模块 | 关键 URL 参数 |
|---|---|---|
| `#/home` | E / training-home | catalog、revision |
| `#/data/:format` | E / data-explorer | catalog、revision、q、source_kind、language、status、offset、limit |
| `#/ingest` | F / ingestion | run_id、batch_id；此页始终操作 workspace |
| `#/datasets/:kind` | G / training-datasets | catalog、revision、dataset_id、version、tab、split、offset、sample_id |
| `#/lineage` | D / lineage | catalog、root_type、root_id、direction、max_depth |
| `#/advanced/assets` | 现有 AssetsPage | 兼容原资产筛选与跳转 |
| `#/advanced/processing` | 现有 ProcessingPage | 兼容原运行查询 |
| `#/advanced/document` | 现有 DocumentComparePage | asset_id |
| `#/advanced/datasets` | 现有 DatasetPage | product_type |
| `#/advanced/dpo` | 现有 DpoPage | 原有 DPO 审核/构建 |
| `#/advanced/admin` | 现有 AdminPage | 原有权限 |

- `format = all | pdf | html | md | txt | docx | csv | json | jsonl | other`；首页展示八类，other 用于成功识别为文本的未知扩展名。
- `kind = cpt | sft | dpo`；API/数据库现有产品类型映射为 `cpt -> pretrain`，其它同名。
- `tab = overview | samples | build`。样本与构建标签也存 URL，刷新后可恢复。
- 各功能导出默认页面组件，由页面读取路由参数并调用 `useWorkspaceContext()` 获取现有 ApiContext；A 提供受保护的父路由。
- 不使用 HTML 原型中的硬编码用户名、剩余容量、活动时间作为业务默认值。

## 3. 共同记录类型

### 3.1 对象与来源

```ts
type Catalog = 'generated' | 'workspace';
type TrainingKind = 'cpt' | 'sft' | 'dpo';
type Split = 'train' | 'validation' | 'test';
type ObjectType = 'source' | 'file' | 'operator_run' | 'segment' | 'sample' | 'dataset_version';
type ObjectRef = { catalog: Catalog; type: ObjectType; id: string };
type SourceKind = 'web' | 'book' | 'paper' | 'other';
```

来源类别不是某个真实公开数据集的名称、作者或授权证明。所有实体均需当前 workspace 的明确归属。

### 3.2 样本

公共字段：`id, workspace_id, kind, dataset_id, dataset_version, sequence, split, source_group_id, source_refs[], segment_refs[], language, char_count, token_count, token_count_method`。sequence 是版本内稳定排序序号；样本按 sequence/id 升序，过滤在分页前完成。

- CPT：`text`，可选 `title`；界面显示单位“篇”。
- SFT：`messages: [{role: 'system'|'user'|'assistant', content: string}]`，保留多轮顺序；界面单位“条”。
- DPO：`prompt, chosen, rejected`，可选 `preference_reason`；界面单位“对”。一对算一个顶层记录，不能将两个回答算两条。
- 不准确的 Tokens 不用 `len(text.split())` 冒充模型分词结果；无已确认分词器时 `token_count=null`，可提供 `char_count`。保留方法字段用于解释统计。
- 只读生成记录的 origin 在 manifest 中明确，不在界面增加“模拟”角标。

### 3.3 文件摘要

`id, workspace_id, filename, format, media_type, size_bytes, source_ref, source_kind, language, ingested_at, processing_status, segment_count, dataset_refs[]`。language/ingested_at/segment_count 可空，文件按 filename/id 升序。

`processing_status = unprocessed | queued | running | succeeded | partial | failed`。没有真实处理记录的文件不能仅根据脚本已生成就被标记为清洗完成。

### 3.4 通用指标与分布

- `Metric = {value: number|null, unit, numerator?: number, denominator?: number, delta?: number|null, comparison_period?: {from,to}}`。
- `Distribution = {measure, unit, total_count, buckets: [{key, label, count, ratio}]}`；互斥桶计数之和必须等于 total_count，含 unknown 桶；空分布 ratio 为 null。
- 时间序列：`{timezone, from, to, unit, points:[{date, count}]}`，缺少接入的日期返回 0；缺少接入时间不能伪造日期填补趋势。
- 文件来源分布按文件计数；片段语言/长度分布按片段计数；训练样本分布按各类顶层记录计数。每张图注明自己的 measure/unit。
- 质量通过率仅基于已完成质量评估的同单位对象；前后周期均无评估依据时 value/delta 为 null。

## 4. B 负责的只读接口

以下路径统一位于 `/training-center`；除特定目录参数外均接受 catalog、revision，身份来自当前 session/workspace。

| 方法与路径 | 请求参数 | 响应主体（均带 scope） | 消费者 |
|---|---|---|---|
| `GET /overview` | catalog, revision | metrics, formats[], datasets[], flow, recent_activities[] | E 首页 |
| `GET /formats/{format}/stats` | from, to, timezone, source_kind, language, status | metrics, flow, ingestion_trend, length_distribution, language_distribution, source_distribution, dataset_refs[] | E 数据台 |
| `GET /files` | format, q, source_kind, language, status, offset, limit | 分页 FileSummary | E |
| `GET /files/{file_id}` | catalog, revision | file, source, processing_summary_ref, dataset_refs[] | E/D |
| `GET /files/{file_id}/comparison` | record_id 可选 | before, after, applied_steps, record_ref, processing_run_ref | E；只返回已存在对比 |
| `GET /datasets` | kind 可选 | items: DatasetSummary[] | E/G |
| `GET /datasets/{dataset_id}/overview` | version | dataset, split_counts, source_distribution, destination_counts, length_distribution, language_distribution, lineage_root_ref | G |
| `GET /datasets/{dataset_id}/samples` | version, split, q, offset, limit | 分页 Sample 联合类型 | G |
| `GET /datasets/{dataset_id}/manifest` | version | manifest 对象与内容哈希 | G/验收 |
| `GET /datasets/{dataset_id}/export` | version, export_format, split 可选 | 下载响应，范围为对应版本和筛选后的全部记录 | G |

- `DatasetSummary`：id, workspace_id, version, version_id, kind, product_type, name, record_count, record_unit, split_counts, token_count, token_count_method, status, source_refs。version 是用户选择的版本字符串，version_id 是 dataset_version 引用的实体 ID；两者不可互换。generated 的 status=available 仅表示内容可读；workspace 保留现有版本状态，不代表自动通过发布门禁。
- `flow`：`{scope_label, stages:[{key,label,count,unit}], transitions:[{from,to,relation,retention_ratio}]}`；仅同单位且确实为子集过滤时填写 retention_ratio，其他 null。
- 所有 stats 过滤参数作用于其声明的同一个 cohort；若刻意展示全工作空间流转，响应明确 scope_label，页面不能误标为当前 PDF 的流转。
- 对比不存在返回约定的 `404 COMPARISON_NOT_AVAILABLE`，页面提示“暂无清洗对比”；不能即时编造一段 before/after。
- workspace 适配器复用已有资产、片段、数据集和版本记录，不从 generated 目录凑数据。已发布 workspace 数据集的导出沿用现有用途/权限规则。
- 数据量上限和流式下载策略见第 9 节；不得把“导出当前页”伪装成“导出全部”。

## 5. C 负责的执行与导出接口

上传和创建处理任务继续使用现有 `/uploads/*`、`/ingest-batches`、`/pipeline-runs/batches`。不改变旧接口返回语义。

新增：

| 方法与路径 | 响应/用途 |
|---|---|
| `GET /pipeline-runs/{run_id}/summary` | status、input/output refs、ordered steps、totals |
| `GET /pipeline-runs/{run_id}/steps/{step_id}/comparison` | 同一 record_id 的 before/after、变化说明；可按 record_id 查询 |
| `GET /pipeline-runs/{run_id}/export?export_format=jsonl` | 已完成阶段的清洗记录下载，默认只允许成功完成的输出 |

处理步骤摘要：

```ts
interface ProcessingStepSummary {
  id: string;
  run_id: string;
  attempt: number;
  operator_key: string;
  operator_version: string;
  config_hash: string;
  sequence: number;
  status: 'queued' | 'running' | 'succeeded' | 'partial' | 'failed';
  input_count: number | null;
  output_count: number | null;
  input_unit: 'file' | 'record' | 'segment';
  output_unit: 'file' | 'record' | 'segment';
  modified_count: number | null;
  filtered_count: number | null;
  failed_count: number | null;
  input_refs: ObjectRef[];
  output_refs: ObjectRef[];
  started_at: string | null;
  completed_at: string | null;
}
```

- 三个本次清洗算子不做拆分/合并；已结束步骤满足 `input_count = output_count + filtered_count + failed_count`。
- `modified_count` 是 output_count 的子集，不能再加到总数；未结束步骤未知计数为 null。
- 解析允许文件变成多个片段，输入/输出不同单位，不套用上述记录守恒公式。
- D 的 operator_run 节点以某次实际 step execution 为 ID；重试 attempt 必须可区分，默认图选择实际产出该 artifact 的一次执行，不累加所有失败尝试的输出。
- 对比结果只提供请求者可见内容；无对应原始记录就显示不可用，不按索引硬配。

### 通用序列化器（C 编写，B 调用）

Python 函数契约：`serialize_records(records, record_kind, export_format) -> SerializedExport`。

- records：可迭代的已授权、已筛选记录；`record_kind = cleaned | cpt | sft | dpo`。
- export_format：`jsonl | markdown | csv | txt`。
- SerializedExport：`chunks: Iterator[bytes]`、`content_type: str`、`extension: str`。
- 文件名、授权、数据版本、审计和 Content-Disposition 由调用方负责。
- JSONL 保留完整结构；CSV 的 SFT messages 用 JSON 字符串单元格，DPO 固定 prompt/chosen/rejected 三个内容列；统一保留 id/source/split 等必要关联列。
- Markdown/TXT 按角色或优选/非优选标签展示，不能丢失对话或成对结构。
- 导出 UTF-8，多行/逗号/引号正确转义。JSONL 下载扩展名 `.jsonl`、Markdown `.md`、CSV `.csv`、TXT `.txt`。
- B/C 使用共同 fixture 检查序列化，不各写一套导出格式逻辑。

## 6. D 负责的图契约

`GET /api/v1/lineage/graph`

参数：`catalog, root_type, root_id, direction=both|upstream|downstream, max_depth=6, max_nodes=200`；上限分别 12 / 500，非法参数返回 422。

响应：

```ts
interface LineageGraph {
  scope: Scope;
  root: ObjectRef;
  nodes: Array<{
    id: string; // 图内唯一，建议 catalog:type:id
    ref: ObjectRef;
    kind: ObjectType;
    label: string;
    description: string;
    status: string | null;
    metrics: Record<string, number | null>;
    detail: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string; // 必须对应返回 nodes[].id
    target: string;
    relation: string;
  }>;
  truncated: boolean;
  truncation_reason: 'max_depth' | 'max_nodes' | null;
}
```

- `source` 始终指数据的上游，`target` 指下游；upstream 查询也不反转边方向。
- 关系代码基线：`provides=提供`、`parsed_by=解析`、`processed_by=处理`、`produced=产出`、`derived_from` 按存储方向规范化后显示“派生”、`included_in=收录`、`split_into=切分`。
- 若现有存储 relation 的方向不同，D 的适配层统一方向并记录映射，前端不猜测反转。
- 已有 `DocumentVersion -> DocumentVersion` 转换可以由持久化 step 插入 operator_run 节点表达，前提是有真实执行证据；节点不对应历史执行时不能标记“已完成”。
- 生成目录先显示真实生成 provenance 与已实际执行的清洗步骤，缺失步骤允许图不完整。
- 深度/节点截断显示明确提示。M0 可不做继续加载；若增加继续加载须定义 cursor，并与前端一起变更契约。
- 所有返回端点都在 nodes 内，未返回的边不发给前端；前端渲染安全文本，不解释描述中的任意 HTML。

## 7. 数据文件与 manifest（B 主责）

目录基线：

```text
.local/training-center/<workspace-id>/<revision>/
  manifest.json
  sources.jsonl
  files.jsonl
  segments.jsonl
  processing-runs.jsonl
  lineage-edges.jsonl
  datasets.jsonl
  source-files/*.txt
  datasets/
    cpt.jsonl
    sft.jsonl
    dpo.jsonl
```

- manifest：schema_version、revision、workspace_id、generator（脚本路径与代码版本）、seed、generation_config、generated_at、content_files（相对路径/SHA256/行数）、counts、split_policy、provenance。
- 同 seed/config/generator 的内容稳定；generated_at 属于运行元数据，不参与数据内容确定性比较。
- source_group_id 在三个 split 中互斥；使用独立局部随机数生成器，不能依赖全局进程随机状态。
- 没有实际执行的 processing-runs.jsonl 可以为空，不为填满血缘图伪造执行历史。
- 生成目录更新采用新 revision 原子切换；请求中的文件必须来自同一版 manifest。
- 服务配置 `TRAINING_CENTER_DATA_DIR`；B 提供需求，A 写入配置与 Compose 挂载。脚本输出不是自动注册到每一个工作空间的全局公开目录。
- fixture manifest 记载生成事实，README/验收文档同步说明。不因 UI 没有角标而删除 provenance。

## 8. 模块间交接清单

| 交接 | 提供方 → 接收方 | 最迟节点 |
|---|---|---|
| 页面壳、主题、DTO、查询键、模块入口 | A → D/E/F/G | M0 |
| 概览/分页/样本的成功、空、错误响应 | B → A/E/G/H | M0 |
| 处理摘要/对比/下载契约样例 | C → A/F/D/H | M0 |
| 图节点、边、截断响应样例 | D → A/H，D 前端自用 | M0 |
| 配置目录、依赖需求 | B/C/D → A | M0 |
| 序列化器与实际执行记录 | C → B/D/F | M1 分批 |
| 生成目录查询适配器 | B → D | M1 |
| 页面独立出口与深链接说明 | D/E/F/G → A | M1 分批 |
| 真实接口替换开发样例 | B/C/D ↔ E/F/G | M2 |
| 检查命令、结果、版本与已知问题 | A～G → H | 每个 PR 与 M3 |

所有交接都带契约版本；存在阻断时指出缺少的字段/行为以及可继续独立开发的部分，不用“等后端好了再说”代替明确依赖。

## 9. M0 收口决定（2026-10-27）

### 统计与引用

- 单位固定为 `file/segment/record/article/pair/byte/token/ratio`。CPT article、SFT record、DPO pair；跨训练类型总数使用 record。计数为非负整数；ratio 在 0–1；未知值保留 null。
- 首页 formats 是 `{format,file_count,unit:'file'}` 的九个文件格式桶，all 仅用于查询；常见八类之外的 other 不可遗漏总数。activities 是 `{id,occurred_at,label,ref}`，没有实际活动时为空。
- destination_counts 冻结为三个 split 的 `{key,count,unit}` 数组，与 split_counts 完全一致；不表示下游模型使用量或外部任务去向。
- 样本来源分布以 source_refs 第一项为主来源，缺失/未知为 unknown；每个样本只计一次，不能按多来源重复累加。source_refs 顺序因此有语义，不得任意排序。
- char_count 按 Unicode 码点：CPT text、SFT 所有 message.content、DPO prompt+chosen+rejected；不含 title/preference_reason。无确认的模型 tokenizer 时 token_count 和方法都为 null。
- 生成目录无接入时间时 ingestion_trend=null，availability.ingestion_trend 为 ingested_at_missing；无文件为 no_files；有依据时为 available。不得用样本分布代替片段分布。
- 文件详情 source 为 `{id,name,kind,author,url,license}`，后三项可空。processing_summary_ref 为 `ProcessingRunRef|null`。`ProcessingRunRef={catalog:'workspace',type:'pipeline_run',id}` 指整体运行；它不是图节点 ObjectRef，operator_run 仍专指某次真实步骤执行。
- ManifestResponse 包装 `{scope,dataset_id,version,manifest,content_hash}`。manifest 是带 schema_version 的来源文档；generated 使用生成器的 `training-center.generated.v1`（可含全目录内容清单），workspace 沿用原物化 manifest，不能拼接生成来源。content_hash 是完整 manifest（含时间）的 UTF-8、排序键、紧凑 JSON、末尾 LF 的 SHA256；不同于排除时间元数据的 revision。

### 处理、图和导出

- ProcessingSummaryResponse 包含 scope、run_id、status、input_refs、output_refs、steps、totals。steps 按 sequence 唯一升序，ID 对应实际 attempt；totals 为每单位一项 `{unit,input_count,output_count}`，只计整个运行边界，不累加串行步骤重复经过的记录。尚未执行时 steps/totals 可空，不等同于成功处理零条。
- ComparisonResponse 包含 scope、before/after（均为 `{record_id,text}`）、applied_steps（步骤 ObjectRef）、record_ref、processing_run_ref、changes 字符串数组。before/after 必须是同一记录；无可见对应记录返回 404 COMPARISON_NOT_AVAILABLE，不返回伪造空对比。
- graph 请求必须给 root_type/root_id。空图可返回所请求 root 和空 nodes/edges；不存在或越权对象仍按 404/403 处理，不能统一伪装成空图。非空图必须包含 root；每条边端点都必须存在，truncated 与 reason 一致。
- 单次目录读取最多 100,000 个顶层训练记录、内容文件累计 100 MiB；超限 413 CATALOG_LIMIT_EXCEEDED。单次下载最多 100,000 条、编码后 100 MiB，超限 413 EXPORT_LIMIT_EXCEEDED；可以下调限制，不可在未经预算复核时扩大。
- 下载响应 Content-Type 必须含 UTF-8，Content-Disposition 使用安全文件名及 filename* UTF-8。默认只下载成功完成输出；失败/未完成运行返回 409 INVALID_STATE_TRANSITION。服务端使用分块序列化，并在发送响应头前完成授权、范围和大小校验（可先写入本次专用临时文件）；不能先发 200 再悄悄截断。前端现有 Blob 下载受上述 100 MiB 上限约束。序列化器实现仍属于 M1。

### 快照、配置和接入责任

- generated revision 不可变，至少保留当前与前一版本；显式退役后 409 SNAPSHOT_EXPIRED。发布者先验证 manifest 完成标记、workspace_id、所有哈希，再原子切换活动指针。没有读取器驱动的自动删除。
- workspace 快照有效期固定 900 秒，按 workspace/catalog 绑定；每个工作空间最多 10 份，容量不足时淘汰最旧快照，所有过期/淘汰请求统一 409。请求期间使用同一冻结数据，清理责任归快照存储服务；读取不续期。M1 实现可先用进程缓存，重启即过期，部署多进程前必须换共享存储或保证快照路由一致。
- Settings 已提供 TRAINING_CENTER_DATA_DIR（默认 `.local/training-center`）、TTL、容量和数据上限。API 可按 `infra/compose.training-center.yaml` 显式挂载只读目录；该可选配置不会自动挂载或重启共享服务。
- Agent 2 实现路径安全与授权：只能解析已授权 workspace/revision，拒绝绝对路径、父目录逃逸和符号链接逃逸；自定义生成输出不自动注册为公开目录。配置存在不等于 HTTP 读取器/快照缓存已经实现。
- 新路由复用 `corpusflow.api.dependencies` 的 db/actor_id/workspace_id/role_required，保留现有策略。main 已支持 SNAPSHOT_EXPIRED、COMPARISON_NOT_AVAILABLE 和超限错误；不添加返回样例的后端占位路由。Agent 2/3/4 提交真实路由后由集成人员注册并更新实际 OpenAPI。

### 统一样例与检查

`contracts/training-center/examples.json` 是 B/C/D 的唯一前端样例包：B 的固定种子 23/11/7 与全空数据重放；C 是明确标注 synthetic 的协议样例；D 是 B 来源/文件关系的投影及 max_nodes 截断样例。C 的成功状态只表达协议，不是持久化执行事实。原 Agent 2 proposal 文件保留为可重放来源，不再作为公共类型定义。

`python scripts/export_training_center_contract.py --check` 检查生成 TypeScript/设计 OpenAPI 是否过期；`python scripts/build_training_center_examples.py --check` 检查样例漂移。`tests/contract/test_training_center_baseline.py` 校验请求与响应、OpenAPI 结构/引用、计数/范围/图语义、UTF-8 下载字节和真实 FastAPI 参数解码。

浏览器只在 DEV 且 VITE_TC_FIXTURES=true 时使用统一样例，不回退真实请求。普通 workspace、认证、写入和下载走真实接口。C 的只读样例还要求 `fixture=contract-v1` 和保留的 m0-example-run/step ID；真实运行 ID 永不拦截。样例未覆盖的统计过滤明确 422，未覆盖路由仍走网络；这不代表业务实现可忽略这些过滤。
