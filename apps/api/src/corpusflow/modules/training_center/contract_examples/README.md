# Agent 2：M0 生成目录与响应建议

> 历史提案来源已纳入契约 1.0.0。公共类型以 `corpusflow.contracts.training_center` 为准，统一场景包位于仓库根目录 `contracts/training-center/examples.json`，冻结决定见共享契约第9节。下文保留首轮交付说明和可重放来源；其中待确认事项已由冻结决定取代。

基于共同基线 `263821e` 的 `TRAINING_CENTER_CONTRACT_V1.md` 草案。本目录由 Agent 2 维护，供 Agent 1 评审后整合到共享 DTO 和开发样例。**本轮没有实现或注册 HTTP 接口，也没有实现 React 页面、数据库写入或真实处理链。** 不得在后端失败时自动返回这里的成功样例。

## 运行与重放

生成器仅使用 Python 3.12 标准库，不需要新依赖、模型服务或网络。仓库根目录运行：

```powershell
python scripts/generate_training_center.py --workspace-id tc-agent2 --seed 42
python scripts/generate_training_center.py --workspace-id tc-agent2 --seed 42 --cpt-count 23 --sft-count 11 --dpo-count 7 --output-dir .local/training-center/my-small
python scripts/generate_training_center.py --workspace-id tc-agent2 --seed 42 --cpt-count 0 --sft-count 0 --dpo-count 0 --output-dir .local/training-center/my-empty
```

不指定 `--output-dir` 时输出为 `.local/training-center/<workspace-id>/<revision>/`。指定时表示**最终新目录**，必须位于当前 worktree 的 `.local/training-center/` 内。输出路径不参与配置哈希；同一配置可在两个新目录重放。已存在的目录（包括空目录）或文件一律报错退出 2，不提供覆盖开关。workspace ID 只接受 1–64 位 ASCII 字母、数字、下划线、连字符，拒绝路径和 Windows 保留设备名；seed 为整数，数量为非负整数。

响应建议从完整生成文件读取；示例导出需要项目已安装（例如 `uv sync --frozen --group dev`），或将 `apps/api/src` 加入 PYTHONPATH：

```powershell
.venv/Scripts/python.exe -m corpusflow.modules.training_center.contract_examples.build --normal-dir .local/training-center/my-small --empty-dir .local/training-center/my-empty --output-dir .local/training-center/my-responses
```

这个命令同样拒绝已存在的输出目录。提交的 `normal.json` / `empty.json` 来自 seed 42、workspace `tc-agent2`，数量分别为 23/11/7 和 0/0/0；`provenance` 保留配置、版本、revision 与实际生成时间。测试重新生成内容并重放捕获时间，逐字段对照提交样例；统计不是手写常量。`errors.json` 为错误场景建议，没有伪装成实际 HTTP 调用结果。

## 生成模型与可复现性

| 文件 | 实际含义 |
|---|---|
| `sources.jsonl` | 每个来源组一条通用来源，类别 web/book/paper；author/url/license 均为 null |
| `source-files/*.txt` | 实际存在的 UTF-8 模板来源文件；类别为 book 不意味着文件是 PDF 或真实书籍 |
| `files.jsonl` | 每个实际来源文件一个摘要；内部 relative_path 可读且参与哈希，API 样例不暴露它 |
| `datasets.jsonl` | 本轮新增建议：三个数据集版本实体，使 dataset_version 引用有可解析目标，空数据集也存在 |
| `datasets/cpt.jsonl` | 顶层一行一篇；text 为正文，title 不计入 char_count |
| `datasets/sft.jsonl` | 顶层一行一条；messages 保留 system/user/assistant/user/assistant 的顺序 |
| `datasets/dpo.jsonl` | 顶层一行一对；prompt/chosen/rejected/preference_reason 不拆行计数 |
| `segments.jsonl`、`processing-runs.jsonl`、`lineage-edges.jsonl` | 空；本轮未执行解析或清洗，不虚构片段、算子或执行边 |

所有实体有 workspace_id；样本保留契约的全部公共字段。ObjectRef 使用 `{catalog,type,id}`；来源引用指向真实生成的 source，segment_refs=[] 明确表示未生成片段。file.dataset_refs 与 overview.lineage_root_ref 指向 datasets.jsonl 的 version_id。跨对象图展开留给后续适配，当前不声称图 API 已实现。

文件状态为 unprocessed，ingested_at=null；生成不等于真实上传。dataset.status=available 仅表示生成内容可读，不表示审核、发布或质量通过。kind=cpt 只用于训练中心视图；对应 product_type 始终是 pretrain。

每种记录数量先按 90/5/5 做整数最大余数取整；余数相同时按 train、validation、test 顺序分配。再在每个预算内创建最多 5 条样本的来源组，末组可不足 5 条。此算法是**规划生成来源组**，不是对外部既有来源组切分；既有组的后续导入不得使用本算法拆组凑数。组 ID 在不同 kind 之间也互不重用。例：1→1/0/0，7→6/1/0，10→9/1/0，23→21/1/1。

默认规模：CPT 2000（1800/100/100），SFT 1500（1350/75/75），DPO 800（720/40/40）。共 4300 个顶层训练记录、860 个来源文件、860 个来源、0 个片段；DPO 的 800 对在跨类型顶层记录统计中贡献 800，而不是 1600。默认产物与其他批量数据均在 Git 已忽略的 `.local/`，不提交。

局部 `random.Random(seed)` 不改变全局 RNG。UUIDv5 的命名空间由 workspace/seed/配置/schema/生成器版本决定；同配置 ID 稳定，配置或工作空间变化会改变 ID。生成器版本显式为 1.0.0，后续改变输出算法/模板必须升级版本。JSON 使用 UTF-8、排序键、固定分隔符和 LF；不使用平台默认编码/换行。manifest.content_files 覆盖所有内容文件（包括 TXT）的 SHA256、字节数、物理行数；空 JSONL 为 0 行。

revision = 对 manifest 除 revision/generated_at 外的规范 JSON 求 SHA256；generated_at 为真实 UTC 运行元数据，不影响内容与 revision。manifest 自身不参与 content_files，避免循环哈希。写入时独占创建新目录，所有内容完成后原子重命名 manifest.json.tmp 为 manifest.json，后者作为完成标记；失败残留目录保留且不可复用。**本轮未实现服务端 active revision 指针切换**，读取方必须拒绝没有 manifest 的目录并完成哈希验证，发布方只可切换到已验证目录。

内容为有限模板组合，适合开发验证，不是高多样性的生产训练语料；分组隔离不代表跨组近似重复检测已经完成。

## 响应字段与单位

每个 JSON 文件是场景包：`responses.<name>={request,status_code,body}`。只有 body 是建议的 HTTP 响应主体；proposal_version/provenance/request 等是开发样例元数据。客户端的真实工作空间身份应来自 Bearer 与 X-Workspace-ID，不信任请求体传入的 workspace。

| 场景名 | 契约路径（前缀 /api/v1/training-center） | 字段说明 |
|---|---|---|
| overview | /overview | metrics 为命名 Metric 映射；formats 按文件数统计，datasets 为三类摘要，flow 为各单位数量，recent_activities=[] |
| txt_stats | /formats/txt/stats | metrics 为 TXT 同一来源范围；source_distribution 按文件，length/language_distribution 按片段；关联训练数按 source_ref 去重关联 |
| files | /files?format=txt | scope/items/total_count/offset/limit；total_count 为筛选后文件总数，与分页大小无关 |
| cpt/sft/dpo_overview | /datasets/{id}/overview | dataset、split_counts、来源/长度/语言分布；destination_counts 暂建议表达三个 split 的顶层记录数 |
| cpt/sft/dpo_samples | /datasets/{id}/samples | 顶层样本联合结构，默认 offset=0/limit=20；cpt_samples_next 为 offset=20 的第二页 |

- scope 使用契约全部字段。generated 的 as_of 暂取实际 manifest.generated_at；metric_definition_version 使用带 proposal 标识的建议版本，等 Agent 1 冻结。
- 建议 unit：file/segment/record/article/pair/byte/token/ratio；显示标签由前端映射。跨类型 training_record_count 使用 record，单类 CPT 为 article、SFT 为 record、DPO 为 pair。
- char_count 是 Unicode 码点数：CPT 仅 text；SFT 各 message.content 之和；DPO prompt+chosen+rejected，不含偏好理由。长度桶为 0–127 / 128–255 / 256+ 码点；**不是 Tokens**。所有 token_count/token_count_method=null。
- 所有分布含 unknown 桶，互斥桶之和等于 total_count；空分布 ratio=null。单类来源分布每样本仅计一次，以第一项 source_refs 为主来源；生成器每样本仅有一个 source，未来多来源需要先确定主来源规则。
- 文件没有接入时间，ingestion_trend=null 且 availability 给出原因，不伪造 30 天时间序列。空目录同样用 null/no_files；未来存在真实时间范围且无事件时再填 0 点。
- quality_pass_rate.value/delta=null；不把没有评估当作 0% 或 100%。flow 不跨单位计算保留率；transitions=[]，不推断解析/清洗已执行。
- files 按 filename,id 升序；samples 按 sequence,id 升序。sequence 是建议新增的稳定排序字段。超出 total_count 返回空页，offset<0 或 limit 不在 1–100 返回 422。
- 空场景保留三个空数据集，全部数量为 0、分页 items=[]；未知指标为 null。不存在的数据集应返回 404，不能伪装成已有空数据集。
- 错误 envelope 对齐 core/errors.py：error.code/message/details/retryable + request_id，无 scope。errors.json 覆盖每种响应的 409 SNAPSHOT_EXPIRED，另含 403/404/422；422 使用现有 VALIDATION_FAILED。retryable=false 表示不要原参数自动重试，409 需要刷新整个查询快照。

## 现有实现核对

核对了 `services/dataset_builders.py`、`db/models.py`、`api/v1/business.py`、`core/errors.py` 和 `main.py`：

- 产品类型现为 sft/pretrain/rag/evaluation/dpo，PretrainBuilder 以 source_id 聚合片段；无需也不能新增 cpt 数据库枚举。
- CandidateSample.payload 保存产品结构，SampleEvidence 关联 Segment；DatasetVersionSample 保存 split。DPO 由已 approved 的 PreferenceSample 构建，生成记录不能绕过该流程进入 workspace 发布。
- 旧 `/datasets/{id}/samples` 默认 limit=50、上限 200，返回 payload 包裹；搜索在分页后执行，total_count 未包含关键词条件。新接口应在同一过滤集合上计算总数后分页，不能直接透传旧接口结果。
- 旧 DatasetVersion.token_count/tokenizer_version 可能来自 builtin-whitespace-1；新训练中心适配时应保持 null 或明确为旧估算，不可将该值冒充已确认模型分词数。
- actor_id 校验有效用户，workspace_id 校验 active Membership；role_required 控制角色。对象不存在用当前 workspace 条件查询后 404，未加入工作空间 403。只读生成目录仍需授权，不因本地有文件就公开。
- 已发布版本下载还受 `_version_authorized` 的来源 LicenseGrant.purpose/status=confirmed 检查；新 workspace 导出必须保留，不与 generated 混合。

## 需要 Agent 1 确认/补齐

1. 认可 datasets.jsonl 与 source-files/*.txt 的附加目录结构，以及 version_id、workspace_id、sequence、product_type 等建议字段；确定 generated dataset.status=available、单位枚举和 Metric 的命名 key。它们目前只是本模块模型，未修改共享 DTO。
2. 确认 ingested_at/token_count_method/ingestion_trend 的 nullable 类型和 availability；as_of 使用 generated_at 是否合适。格式页无片段时应展示空分布，而不是用训练记录替代片段。
3. 明确 destination_counts 是否指 split 去向。本轮使用 split；若要表示下游任务/模型用途，当前没有执行证据，应改为 null/空，不填虚构使用量。确认多 source 样本的主来源/多值分布口径。
4. 明确 metric_definition_version、char_count 边界与排序字段。确认三类空数据集的表现、全格式 9 个桶（首页只展示 8 个常见格式，other 单列或汇总）和 source_ref 关联 cohort 规则。
5. 提供认证/db 依赖的共享兼容入口并注册新路由；不要让各模块重构 business.py。main.py 的现有 HTTPException known 集合**不含 SNAPSHOT_EXPIRED / COMPARISON_NOT_AVAILABLE**，会被改为 HTTP_ERROR/NOT_FOUND；需提供统一错误支持或明确使用现有 error_response 的方式。
6. 配置 TRAINING_CENTER_DATA_DIR 指向 `.local/training-center`，服务按授权 workspace/revision 查找，校验 manifest.workspace_id 并禁止路径穿越；自定义输出目录需手工登记到工作空间映射，不自动成为全局目录。不需新增 Python 依赖。
7. 快照保留建议：generated revision 不可变、至少保留当前与前一版本，显式退役后返回 409；workspace 统计快照建议固定 TTL 15 分钟、绑定授权工作空间和 catalog，过期统一 409，所有列表/统计共用一份冻结数据。TTL、存储介质、容量上限和清理责任需确认，本轮未实现缓存/快照服务。
8. 数据规模与导出建议：初版离线生成/读取按默认 4300 条做验收，不声称支持任意大规模；生产读取上限/内存预算待定。导出使用 Agent 3 的流式 serialize_records，筛选后全量导出且最大行数/字节数需在 M0 确认，不能以当前页代替全量。

## 下一轮依赖及验证边界

Agent 1：冻结共享契约/DTO、依赖入口、错误 code 与目录配置/路由注册。Agent 3：真实解析/清洗记录、导出序列化器；本轮不依赖其处理链即可浏览生成样本。Agent 4/人工：独立复核来源分组与引用，并接入生成来源/数据集节点；本人测试不替代独立验收。

测试命令与实际结果见 [VALIDATION.md](VALIDATION.md)。本轮未运行真实 HTTP、数据库、Worker、前端或旧构建流程的集成回归；没有实现这些接口，因此本目录测试通过不等于真实 API 验收通过。
