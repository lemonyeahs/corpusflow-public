# Agent 1 公共接入请求（基线 acb7ce0）

状态：2026-10-27 审查后提出；以下依赖尚未交付或确认，不能视为真实联调通过。Agent 1 仅在 `feat/tc-shell-explorer` 工作，不自行合并其他开发分支。

## Agent 2：workspace 查询与文件关联

1. 保留 generated 9 个 GET 的响应、授权和统计口径，实现同路径的 workspace 适配器。目前 Reader.query 对 workspace 返回 503 ADAPTER_UNAVAILABLE。
2. 首次 overview/files 查询原子捕获 workspace 快照；所有 stats、datasets、file detail 读取同一冻结投影。不能只冻结 revision/as_of 再查询实时 ORM 数据。
3. FileDetail.processing_summary_ref 只能来自该 file 的真实持久化关系（例如 PipelineRun.asset_id），不可任选最近一次 run。请说明多运行时的选择规则及稳定排序。
4. 按冻结契约实现 `/training-center/files/{file_id}/comparison?catalog=workspace&revision=...&record_id=...`：在服务端验证 file→run→step→record 关系，并委托 Agent 3 读取真实前后记录。record_id 可选；缺少明确默认映射时返回 404 COMPARISON_NOT_AVAILABLE，不选择数组首项。无需另增未经确认的 DTO 字段。
5. 确认 stats 不给 from/to 的趋势时间范围；前端当前取响应最后 30 个 UTC 日，q 仅过滤文件列表。

## Agent 3：处理 router 注册前的必需修正

基线中 `api/v1/processing_insights.py` 未注册；以下问题解决并通过契约/真实存储验证后，Agent 1 才注册并生成实际 OpenAPI：

| 接口/字段 | 当前实现 | 要求 |
|---|---|---|
| summary / scope | 忽略 catalog/revision，返回 PipelineRun.revision；运行未完成时 as_of 使用当前时间 | 使用统一 workspace 快照；显式响应模型、Query DTO；处理运行的 revision 不可冒充统计快照 |
| steps[].input_refs/output_refs | 把最终版本片段用于各步骤，previous_refs 顺序推导 | 使用对应 step/attempt 的真实持久化输入输出映射；证据缺失保留未知/不可用，不回填最终片段 |
| sequence/attempt/timestamps | 依据 created_at/id 排序，用整个 run.finished_at 作为步骤完成时间 | 以真实执行序列、attempt 和步骤时间记录为依据；无依据时间为 null |
| steps counts / totals | 未执行时仍可能输出文件/片段总量；失败数量推断 | 只输出可验证边界统计；未知为 null，符合冻结的单位与守恒约束 |
| comparison | 总是 COMPARISON_NOT_AVAILABLE，未读取真实对比记录 | 保存并查询同一 record 的 before/after；验证 run/step/record/workspace；无证据仍 404 |
| export | 允许 partial；全量读进 list，未做编码字节/条数预检 | 默认仅 succeeded；发送响应头前验证授权、记录范围、100000条/100MiB上限；错误必须保持非200 |
| export headers | JSONL 不含 charset；仅 filename | UTF-8 Content-Type、安全 filename 与 filename*，完整保留结构/关联信息 |
| HTTP/OpenAPI | 返回 dict/None，无完整查询与响应声明 | 使用冻结响应/请求模型，声明授权头、安全方案、错误包裹及下载媒体类型 |

请交付：本分支可审查的提交、真实持久化映射依据、定向测试及隔离执行结果。Agent 1 不修改 Worker、数据库模型或迁移。

## Agent 2＋4（并供 Agent 3 消费）：统一快照规则

以下是契约第 1、9 节的落实要求，不改变 wire 字段。当前图使用独立 GraphSnapshots，而处理摘要使用 run revision，二者尚不能与目录快照互通。

1. **唯一发行方/存储**：Agent 2 提供 workspace 快照服务和冻结投影；Agent 4/3 使用同一服务。接口形态由提供方提交，禁止每个模块建立同名 revision 的独立缓存。
2. **revision**：服务端生成不透明、不复用的快照 ID，绑定 workspace/catalog=workspace。既不是 run.revision，也不是 generated manifest hash。客户端不解析 ID、不替换或自动重试不同快照。
3. **as_of**：同一快照固定 UTC 捕获时间，metric_definition_version 固定；所有端点返回完全一致的 Scope。捕获须在同一数据库一致性边界内完成。
4. **冻结内容**：目录、处理证据和图投影在初次捕获时共同冻结。禁止在旧 token 下延迟从新数据库状态补某模块的数据；缺少模块能力返回 503 ADAPTER_UNAVAILABLE，不能发假空结果。
5. **有效期/容量**：创建起 900 秒，读取不续期；每 workspace 总计最多 10 份（不是每模块各10份），按创建顺序淘汰最旧。未知、过期、淘汰、重启丢失、跨空间 token 统一 409 SNAPSHOT_EXPIRED，先重验当前身份和成员权限。
6. **跨页传递**：首页→数据台→数据集→文件→处理/血缘携带原 catalog/revision；刷新整个目录查询后移除 revision/offset/已选详情再重新捕获。换空间/目录丢弃旧 token。接入页用于实时轮询的 run revision 不写进统计 URL。
7. **兼容过渡**：当前独立图 token 只用于图内。统一服务接通前，从图到目录、目录到图应重新取得目标模块快照并明确不是同一快照；不得回显旧 token 到新查询来制造一致。由 Agent 1 处理公共导航，Agent 4 调整图内往返链接。
8. **部署**：进程内实现仅适用单进程；多进程须共享存储或按 snapshot 粘性路由。缺少共享存储时不宣称多实例一致。

验收交给 Agent 4：固定 token 后修改数据库，逐页读取必须保持原内容及 as_of；第11份淘汰第1份，读取不能改变淘汰顺序；900秒边界失效；撤销成员立即失去访问；跨空间、重启、模块缺失分别给约定错误。

## Agent 1 继续完成的公共工作

共享客户端校验完整 scope；文件对比交给文件限定接口，不再由浏览器猜步骤；文件详情按显式 run 引用展示真实摘要并拒绝范围/归属不匹配；修复公共权限/未就绪错误提示，补浏览器和默认应用契约验证。独立测试响应仅验证前端行为，真实 workspace/处理验证在依赖到位前标为未运行。
