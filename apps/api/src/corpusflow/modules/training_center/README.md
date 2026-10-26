# Agent 2：M1 目录读取、workspace 快照与数据集页面

M0 基线：`58fe070`，共享契约/统计口径 `1.0.0`。本轮已将远程 main 的 `c62b570` 合入 Agent 2 分支（合并提交 `2384753`），包含 Agent 3 通用序列化器和 Agent 4 页面。首批 generated API 为 `7e2f227`；workspace/页面为 `78a706e`。

本模块提供 generated 文件读取、workspace 数据库适配、查询服务和导出。业务响应不导入开发样例。指定基线 `acb7ce0` 已在默认 `create_app` 注册本 router，契约测试直接使用默认应用，不再重复挂载。generated 的真实 PostgreSQL/API/前端验收见 [M1 集成报告](../../../../../../docs/reports/TRAINING_CENTER_M1_INTEGRATION.md)；该报告不替代本分支新增 workspace、导出和页面的验证。React 页面由现有入口自动发现。

## 文件与接口

- `catalog.py`：生成 v1 目录的限额读取、完整性/引用校验、发布/退役、解析结果缓存；无数据库依赖。
- `query.py`：同一快照内的统计、搜索、过滤和稳定分页。
- `workspace.py`：现有数据库实体的只读适配，冻结快照及固定有效期缓存。
- `downloads.py`：真实 manifest 校验、导出授权、限额和临时文件；调用 Agent 3 的序列化器。
- `api/v1/training_center.py`：独立 router；复用 `api.dependencies` 的 db/actor_id/workspace_id。每次请求验证用户及 active Membership，viewer 可以读取自己有权限的空间。

路径前缀 `/api/v1/training-center`，下列 GET 路由已实现并通过 HTTP 测试：

| 路径 | 行为 |
|---|---|
| `/overview` | 九种文件格式、三类数据集、实际数量与流转阶段；未知 Tokens/质量为 null |
| `/formats/{format}/stats` | format/all、来源/语言/状态/时间过滤，文件及关联记录同范围统计 |
| `/files` | format、q、source_kind、language、status，filename/id 升序分页 |
| `/files/{file_id}` | 文件、通用来源、关联数据集版本；无处理则 processing_summary_ref=null |
| `/files/{file_id}/comparison` | 先验证文件可见性；本批没有真实对比，返回 404 COMPARISON_NOT_AVAILABLE |
| `/datasets` | kind 筛选，按 CPT/SFT/DPO、id/version 排序 |
| `/datasets/{dataset_id}/overview` | 记录数、split 去向、来源/字符长度/语言分布 |
| `/datasets/{dataset_id}/samples` | 必填 version；split/q 先过滤再分页，sequence/id 升序 |
| `/datasets/{dataset_id}/manifest` | 完整来源 manifest 及其规范序列化 SHA256；与排除时间的 revision 区分 |
| `/datasets/{dataset_id}/export` | JSONL/Markdown/CSV/TXT；当前版本的完整 split，返回下载文件 |

所有读取接口接受 catalog/revision，返回冻结 DTO。generated 未提供 revision 时读取显式发布的活动版本，workspace 则创建新的数据库快照；前端收到后使用 pinScope 固定。提供 revision 时保持该快照。越界 offset 返回空 items 和真实总数，limit 为 1–100。

files.q 仅匹配 filename（Unicode casefold）；samples.q 匹配 CPT title/text、SFT 各轮内容、DPO prompt/chosen/rejected/preference_reason，跨字段以换行分隔，均先过滤再计算 total_count。DPO 一对计一个顶层记录。

stats 的 from/to 是 UTC 时间戳、包含端点；未知 ingested_at 的文件无法满足时间过滤。timezone 使用 IANA 名称，非法时区、倒置范围返回 422 INVALID_ARGUMENT；有真实时间依据时按该时区日期补零。为避免无限展开，单次日序列最多 3660 天；超过返回 422 INVALID_ARGUMENT。无文件或缺失接入时间按契约返回 null 与 availability，不能生成历史趋势。当前生成器没有接入时间，正常结果为 ingested_at_missing。

文件来源分布按文件；generated 没有片段，workspace 片段来自每份 Document 最新 DocumentVersion 的真实 Segment。训练分布按相应顶层记录，主来源取 source_refs 第一项。generated 格式过滤后的记录按 source_ref 关联；workspace 按真实 evidence→segment→document→asset 关联，避免同来源的其他文件被误计。没有实际转换证据时 transitions=[]。

## Workspace 数据库适配

复用 Source、Asset/AssetBlob、Document/DocumentVersion/Segment、PipelineRun、Dataset、DatasetVersion、DatasetVersionSample 和 CandidateSample；不新增表或迁移。CPT 对应 `product_type=pretrain`。只纳入已发布且明确关联到版本的训练记录，不统计草稿或未关联候选；计数从关联记录重算，不信任历史聚合数。一个候选被不同已发布版本使用时，按各版本分别计数。

PostgreSQL 使用独立 REPEATABLE READ 事务，SQLite 显式 BEGIN。样本、文件、来源和关联在一次读取中冻结；缓存返回深拷贝。快照最多存活900秒、每空间最多10份，可由现有配置下调；读取不续期。过期、淘汰、重启或其他空间的 revision 均返回409 SNAPSHOT_EXPIRED。**当前是进程内缓存，多进程部署前需共享存储或固定快照路由。**

文件时间取 Asset.created_at，处理状态和 processing_summary_ref 来自真实 PipelineRun；没有运行就不制造成功状态。所有关联按 workspace 约束。缺失或跨空间 evidence 返回409 INVALID_SAMPLE_EVIDENCE。旧 whitespace token 数据不作为模型 Tokens，保持 null。当前统计采用“每份文档最新版本”的片段口径，已发布样本仍可引用历史片段；请 Agent 1 确认该口径。

训练记录上限及累计内容字节限额使用现有 Settings；元数据实体查询同样受记录数和原始字段字节预算约束，逐条读取、超限即413。单个数据库字段仍由驱动一次取回，超大字段的服务器端投影限制是后续规模化优化点。

workspace manifest 读取原发布版本记录指向的对象，限定读取字节数并校验原 manifest_sha256；随后计算契约要求的完整规范 JSON content_hash。对象存储不可用明确503，不重建或拼接生成 manifest。

## 数据集导出

`export_format=jsonl|markdown|csv|txt`，必填 version，可选 split，固定当前 catalog/revision。没有 offset/q 参数：导出当前版本指定 split 的全部记录；不将当前页冒充全集。直接调用 `corpusflow.services.processing_exports.serialize_records`，没有复制格式逻辑。

workspace 每次下载重新检查版本仍已发布，以及完整版本所有证据文件的 training confirmed LicenseGrant；固定旧快照也不能绕过撤销授权。无可证明授权的文件则403 DOWNLOAD_NOT_AUTHORIZED。generated 使用当前 workspace 成员权限，不虚构授权记录。

序列化完整完成、记录/字节限额和审计写入成功后才返回200响应头。先写 SpooledTemporaryFile（超过1 MiB落临时磁盘），再64 KiB分块发送，完成/异常时关闭；超限413 EXPORT_LIMIT_EXCEEDED。文件名采用UTF-8 Content-Disposition。审计保留目录、revision、split、格式和实际记录数。

## React 页面与旧构建流程

入口 `apps/web/src/features/training-datasets/index.tsx`；无需修改 App.tsx。支持 CPT/SFT/DPO 的目录/版本选择、概览分布、split和文本过滤分页、原始顺序SFT消息、DPO并排回答、manifest及四格式下载。URL和查询键绑定workspace/catalog/revision；快照过期可整体刷新，错误不会换成开发样例。

管理员/工程师可以进入工作空间构建页，复用原 DatasetPage/DpoPage 的审核/校验/发布流程。DatasetPage 仅增加可选 initialProductType；CPT 使用 pretrain，优先选同类型真实workspace数据集。生成目录ID不会传入构建请求。原高级入口保持默认行为。

## 生成、验证和显式发布

工作空间 ID 必须对应真实授权空间；下面 `tc-m1-local` 只是本地命令验证使用的生成目录名，不自动创建 Membership 或数据库实体。

```powershell
# 在仓库根目录；已存在的生成目录不可覆盖
python scripts/generate_training_center.py --workspace-id tc-m1-local --seed 142

# 将上一条输出的 revision 传入；数据根目录可与 Settings 一致
.venv/Scripts/python.exe -m corpusflow.modules.training_center.catalog publish --workspace-id tc-m1-local --revision <revision>
```

`--data-dir` 默认 `.local/training-center`，可指向部署配置的根目录。发布者是本地管理员/部署工具，不是 HTTP 调用者。API 的可选只读挂载不允许执行 publish；应在生产者目录完成后让读取方看到新目录和原子更新的索引。

读取布局为 `<root>/<workspace>/<revision>/manifest.json`，只允许规范 workspace 和 64 位小写 SHA256 revision。自定义输出目录不能直接通过 URL 读取，需先由部署者放入规范布局。

每个工作空间有一个 `catalog.json`（schema `catalog-index.v1`）：

- `workspace_id`、`active_revision`、`previous_revision`；
- `revisions`：已验证并发布、仍可读取的 revision；
- `retired_revisions`：明确退役的 revision，不自动复活；
- `manifest_hashes`：对应 revision 的完整 manifest 哈希，发布后连时间元数据也不能改变。

publish 全量校验候选版本后，通过同目录临时文件、flush/fsync 和 os.replace 原子更新索引。重复发布当前未变化版本无操作，失败保留旧指针。至少保留当前和前一版本；旧版本不会自动删除，退役操作只变更索引：

```powershell
.venv/Scripts/python.exe -m corpusflow.modules.training_center.catalog retire --workspace-id tc-m1-local --revision <old-revision>
```

当前及前一版本禁止退役；更旧的版本才可显式退役。请求退役或未发布 revision 返回 409 SNAPSHOT_EXPIRED。没有索引/目录返回 404 NOT_FOUND，不把它当作合法空数据集。索引是**单管理进程写入**协议；同一实例使用锁保护，多进程发布必须由部署者串行化。API 多进程只读索引不需要共享内存缓存。

## 完整性、限额与缓存

集成修复要求 generated-v1 恰好含 CPT/SFT/DPO 各一份数据集，空目录也保留三类实体；索引发布前按读取端相同的 1 MiB 上限检查。文件采用最多 64 KiB 分块读取，保持完整 SHA256 与读取期间增长超限检测，避免 Windows 小文件按整目录限额反复分配缓冲。

校验 manifest 内容 revision、完整内容清单哈希、物理行数、字节数、workspace 归属、各实体唯一 ID、样本类型/字符数、来源组 split 隔离、source/dataset_version 引用和计数。拒绝重复 JSON key、非法 JSON、绝对路径、父目录穿越、符号链接及 Windows junction；同根目录内指向别的工作空间的链接也拒绝。

按 Settings 限制单目录顶层训练记录最多 100000 条、内容文件累计 100 MiB，可下调不能放大。manifest 和索引也有有界读取，超限返回 413 CATALOG_LIMIT_EXCEEDED。内容/引用/已发布元数据损坏返回 409 CHECKSUM_MISMATCH，不泄露磁盘路径或切换目录。当前 v1 读取器只接受没有处理产物的生成目录；非空 segments/processing-runs/lineage-edges 返回 503 ADAPTER_UNAVAILABLE，等待 Agent 3/4 的持久化结构接入，不忽略它们再声称没有处理。

按 workspace/revision/manifest hash 缓存已解析快照，进程内最多 2 份。每次 load 仍逐文件检查实际字节与 SHA256，即使大小/mtime 未变化也能检测损坏；返回深拷贝避免调用方污染缓存。缓存优化的是模型解析，不省略完整性检查，因此大目录需要后续基于实际负载做性能评估。每个请求只使用一次加载的快照完成查询；发布切换不会混拼同一响应的数据。

目录发布者必须独占管理目录、按不可变版本追加，不得在读取期间修改内容或置换路径；读取方进程只读。文件系统所有者的并发恶意路径置换不属于 HTTP 身份边界，部署者仍须正确设置目录权限。

## 应用集成（已完成）

Agent 2 原交付未改共享入口；以下接入已由集成负责人完成。后续部署仍需指向对应环境的真实授权工作空间和已发布目录：

1. `create_app` 已注册 `corpusflow.api.v1.training_center.router` 一次，不应重复注册。
2. `docs/api/openapi.json` 已更新，含 Bearer 认证、X-Workspace-ID、成功与错误响应；设计 OpenAPI/DTO 本轮无字段变化。
3. 将 TRAINING_CENTER_DATA_DIR 指向已发布的规范目录；只读挂载使用已有可选 Compose 文件，不需新依赖。
4. 使用真实授权 workspace 的 ID 生成/发布目录，关闭开发样例开关后联调首页/数据台；样例的 fixture workspace 不自动拥有授权。

入口中现有注册代码：

```python
from corpusflow.api.v1.training_center import router as training_center_router
# create_app 内，已有业务路由旁
app.include_router(training_center_router)
```

## Agent 4 读取入口

完成 HTTP 授权后，复用同一个 GeneratedCatalog 实例，调用 `load(authorized_workspace_id, revision)`，获得 CatalogSnapshot：scope、manifest、content_hash、sources、files、datasets、samples。samples 保留 source_refs/segment_refs/source_group_id；datasets 的 version_id 才是 dataset_version 引用。接口返回副本，无需自行读取磁盘或使用 proposal 样例。

可以据此展开真实来源→文件和样本→数据集关联；本批没有 operator_run、segment 或已执行边。图节点/边规范化和路由仍由 Agent 4 负责。未来若允许处理后生成目录，请先协调持久化 schema，不直接绕过当前完整性校验。

## 尚待集成与验收

- Agent 1 注册本 router、更新实际 OpenAPI，并确认最新文档片段统计口径；多进程部署需解决快照共享。
- Agent 4 将 generated 图适配接入已授权 GeneratedCatalog；页面已有血缘链接，当前图接口能力由 Agent 4 负责。
- 文件/步骤清洗前后对照仍无稳定记录映射，明确404；不能按数组位置拼接。
- PostgreSQL、真实对象存储、完整构建审核发布与浏览器真实后端联调仍待集成环境验收；SQLite/浏览器fixture测试不替代独立复核。
- 最新远程基线的全仓类型/格式检查问题交对应负责人；具体文件见本轮验证报告。

首批历史记录见 [M1_VALIDATION.md](M1_VALIDATION.md)，本轮见 [M1_WORKSPACE_VALIDATION.md](M1_WORKSPACE_VALIDATION.md)。
