# Agent 1：M2 公共接入与阻断审查

日期：2026-10-27。worktree 为原 `corpusflow-shell`，分支 `feat/tc-shell-explorer`。

## 基线与范围

起始 HEAD 为 `15efe96`，工作区干净，归属正确，无 MERGE_HEAD/rebase/cherry-pick 状态。执行 `git fetch origin` 并确认目标 commit 存在，正常 `git merge acb7ce0fa31befaa203bf1213ad3eebbc4afaa06` 快进到目标，保留历史。未切换 main、未创建替代 worktree、未合并其他开发分支。

先提交接口请求 `4a7d63d`，内容见 [M2 公共接入请求](../plans/TRAINING_CENTER_M2_INTEGRATION_REQUESTS.md)。本次未推送，协作方尚未在此会话确认请求；不要把文档提交视为已完成跨 agent 协议接入。

已验收首页/数据台、generated 9 查询路由保持。本次不修改 Agent 2 数据目录实现/数据集页面、Agent 3 处理服务/Worker/数据库/迁移、Agent 4 图实现，不修改 CI/workflow。

## 已完成的公共变更

- `api/training-center.ts` 提供共享 scopedRequest/queryString；兼容原 training-home 导出。校验 workspace/catalog/revision、UTC as_of 和口径版本；同 revision 的不同资源若返回不同 as_of/口径，拒绝展示并要求整体刷新。请求被取消后不写入范围元数据。
- 首页/格式数据台查询使用该检查；范围冲突与过期均提供整体刷新，避免继续拼接部分统计和列表。
- 文件详情增加 `detail_tab=processing`：仅沿 FileDetail.processing_summary_ref 读取摘要，校验 run_id、完整 scope、input_refs 中的当前文件。无处理证据显示真实不可用，不找任意运行。步骤和边界计数均来自响应，未知值保留未知。
- 文件对比使用契约既有的文件限定 `/training-center/files/{file_id}/comparison`，由服务端负责明确映射，不再按浏览器判断选某个步骤。校验前后记录、record_ref、显式 record_id 及 workspace run 引用；404 COMPARISON_NOT_AVAILABLE 与真实失败分开显示。
- 基线图快照还独立于目录，公共导航及本模块的 workspace 血缘链接不复制不兼容 revision，显示独立快照说明。generated 链接和目录内部固定快照行为保留。统一服务验收后再移除此过渡隔离，Agent 4 的图内链接仍需对应接入。
- `main.py` 公共错误处理对登录、权限、未找到、无效状态、参数错误提供准确中文原因；前端错误展示区分 401/403/503、保留 request_id，权限错误不提供无效重试。
- 默认 create_app 注册门禁测试保证已实现的 generated 路由存在、尚未审查通过的 processing 路由不被发布。实际 OpenAPI 已重新生成，与基线无语义差异；校验其与默认 create_app 完全一致。

wire DTO、契约版本 `1.0.0`、统一样例均无字段变更。UI 新增 `detail_tab=processing`；`scope_reset=1` 仅作跨独立快照导航提示，不传入服务端查询。

## 接口审查结论：不能注册 processing router

`api/v1/processing_insights.py` 不消费冻结的 catalog/revision，summary 使用运行 revision/as_of。`services/processing_insights.py` 把最终片段用于多个步骤，不能证明步骤输入输出归属。comparison 尚无实际实现，export 允许 partial、没有约定的条数/字节预检及完整 UTF-8 下载头。详细字段、代码位置及验收要求已交给 Agent 3 的请求文档。

因此本次没有简单增加 include_router，也没有在实际 OpenAPI 中添加尚未完成的处理能力。默认应用真实请求这些端点仍为 404。前端新增摘要调用是接入准备，不能称为已连通真实处理服务。

## 实际验证

| 检查 | 结果与边界 |
|---|---|
| typecheck / lint / build | 均通过；保留 ECharts 懒加载 chunk 约 589 kB 的既有提示 |
| 受影响后端契约 | `test_training_center.py`、`test_training_center_baseline.py`、`test_training_center_integration_gate.py`：100 passed；目录测试用隔离 SQLite，新增错误测试只验证默认应用错误封装 |
| Python 静态检查 | 修改文件 ruff/format 通过，main.py 的 mypy 通过 |
| DTO / 样例漂移 | 两个生成脚本 `--check` 通过；无需手改生成 DTO |
| 生产样例剔除 | 当前 dist 的16个 JS 文件未检出 fixtureResponse、处理样例 ID 或统一样例 revision；`git diff --check` 通过 |
| 关闭开发样例的浏览器测试 | 完整运行 27 passed / 1 failed / 2 mode-specific skipped；失败发现登录错误标题与描述重复。修复后该场景定向 1/1 passed，28 个适用场景通过 |
| 显式开启样例的浏览器测试 | 11 passed / 19 mode-specific skipped，包含修复后的登录场景 |
| 真实网络回归 | 原隔离脚本 `verify_training_center_m0.py --catalog`：62 项 HTTP 检查与 6 项浏览器全部通过，无请求拦截；保留 generated 和现有 workspace 图的已验收能力 |

首次执行后端 pytest 时因本 worktree 未设置必需测试环境变量，收集被阻止；使用指向不可用本地端口的非敏感测试配置后，100 项通过。不读取或修改共享服务凭据。

真实验证报告：`.local/cf-m1-f245d75bbb28/result.json` 为 passed；数据库为本次新建随机命名 PostgreSQL 容器，运行既有迁移，API 使用独立端口。浏览器覆盖真实登录/空间切换、4300 条 generated 数据、固定/过期快照、workspace 适配器不可用、现有数据库图快照。图验证仍使用显式测试记录，不声称由 Worker 处理产生。API 与专用容器均已停止；未重启/迁移共享服务。

新增 workspace 摘要/对比、同 revision 异 as_of、文件归属拒绝、无处理证据、空数据和权限展示用例使用受控 HTTP 响应，只证明前端检查与交互，不计作真实 workspace 业务联调。

## 未完成依赖与下一步

1. **Agent 2**：workspace 目录适配器、明确文件→run→step→record 映射、文件限定 comparison，统一冻结快照入口。当前 workspace 查询仍为真实 503。
2. **Agent 3**：修正摘要证据与 scope、实现真实 comparison、完成安全有界导出及声明。提交定向测试和隔离真实执行记录后再由 Agent 1 注册。
3. **Agent 2/4（供3消费）**：同一个快照服务/冻结投影，900秒不续期、每 workspace 总共10份、固定 as_of、过期统一409、先重验授权。当前独立 GraphSnapshots 与 run.revision 不能当作该服务已存在。
4. **Agent 4**：图内往返链接接入共享规则，独立复核本轮公共改动并运行跨模块真实验证。

未运行：真实 workspace 首页/数据台/文件关联、真实处理摘要/前后对比/导出、Worker、Redis/MinIO 处理闭环、统一 workspace 快照跨目录/处理/图验收，以及完整旧业务 integration 套件。上述依赖不在本轮授权文件范围内，保留真实错误而不回退样例；本次不标记整个 M2 完成。
