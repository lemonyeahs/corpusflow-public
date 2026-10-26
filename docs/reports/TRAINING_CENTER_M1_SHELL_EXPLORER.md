# Agent 1 M1：首页与格式数据台

> 本文记录 `15efe96` 的前端独立交付。后续已接入 Agent 2 的 generated 只读 API 并开展真实服务验收，最新结果见 [M1 集成报告](TRAINING_CENTER_M1_INTEGRATION.md)。原交付时未运行项保留，不代表当前集成状态。

基线：`58fe070955b3a8c66806dc8f2d8ed2f152d5036d`，分支 `feat/tc-shell-explorer`。契约仍为 `1.0.0`，未修改 wire DTO、后端路由、数据库、Worker 或其他 agent 的页面。

本次是 Agent 1 的 M1 前端交付，不表示四条开发线全部完成，也不计作真实业务 API 验收。

## 实现范围

- 首页：四项指标、八种常用格式及 other 入口、CPT/SFT/DPO 版本卡片、真实响应的流转与活动。
- 数据台：格式/来源/语言/状态筛选、文件名搜索、服务端分页、统计指标、流转、30 天趋势、长度/语言/来源分布、关联数据集。
- 文件详情：来源信息、处理状态、关联版本、血缘及旧原文对照入口；抽屉和标签可通过 URL 刷新恢复。
- 对比：generated 走文件 comparison；workspace 走已有 processing summary/step comparison。文本按纯文本渲染，前后 record_id 必须一致；有显式记录选择时还必须与所选 ID 一致。
- 查询：workspace/catalog/revision/resource/path/filters 完整隔离；首次响应固定 URL revision 后再请求关联资源。快照过期提供整体刷新，不以真实接口错误触发样例。
- 公共修复：切换 catalog 和刷新快照清除旧文件抽屉参数；Ant Design 5 加入 React 19 官方兼容包，版本锁定在 lockfile；ECharts 使用 ESM core 并按图表种类注册。

主要目录：`apps/web/src/features/training-home/`、`data-explorer/`；共享变更限 `app/catalog.ts`、DEV interceptor、入口兼容包与依赖。浏览器测试位于 Agent 1 的 `src/app/__tests__/home-explorer.spec.ts`，不占用 Agent 4 测试目录。

## 页面挂载与共享组件

沿用 `src/app/modules.tsx` 的入口发现机制，不需修改 App.tsx：

| Agent | 默认导出入口 | 路由 |
|---|---|---|
| 1 | `features/training-home/index.tsx` | `#/home` |
| 1 | `features/data-explorer/index.tsx` | `#/data/:format` |
| 2 | `features/training-datasets/index.tsx` | `#/datasets/:kind` |
| 3 | `features/ingestion/index.tsx` | `#/ingest` |
| 4 | `features/lineage/index.tsx` | `#/lineage` |

Agent 3 可从 `features/data-explorer/components/ComparisonView` 导入 `ComparisonView`，props 为 `{comparison: ComparisonResponse}`；完整示例在该模块 README。它只展示传入记录，不负责启动处理或生成内容。

数据台增加 UI 查询参数 `file_id`、`detail_tab=detail|comparison`、`record_id`。这不是服务端 DTO 变更。文件筛选/搜索重置 offset 和选中文件；改变目录清除 revision 及实体参数。数据集链接携带 dataset_id/version，ObjectRef 的 dataset_version ID 通过 DatasetSummary.version_id 解析；找不到时提供血缘入口。

## HTTP 调用与统计范围

以下均相对 `/api/v1`，使用现有 session/workspace 请求客户端：

| 调用 | 参数与用途 |
|---|---|
| `/training-center/overview` | catalog/revision；首页入口固定快照 |
| `/training-center/files` | catalog/revision/format/q/source_kind/language/status/offset/limit；数据台入口固定快照 |
| `/training-center/formats/{format}/stats` | catalog/revision/timezone=UTC/source_kind/language/status；包含 all、other 查询 |
| `/training-center/datasets` | catalog/revision；解析关联版本，不拿列表页行数计算统计 |
| `/training-center/files/{file_id}` | catalog/revision；详情 |
| `/training-center/files/{file_id}/comparison` | generated 的 catalog/revision/record_id（可选） |
| `/pipeline-runs/{run_id}/summary` | workspace 的 catalog/revision；读取已有步骤 |
| `/pipeline-runs/{run_id}/steps/{step_id}/comparison` | workspace 的 catalog/revision/record_id；读取已有对比 |

`q` 只属于 FilesQuery，页面明确说明搜索不改变上方统计。来源、语言、状态同时传给列表和统计。关联数据集显示其整个版本总量，不能当作筛选后的记录数。

趋势展示服务端 TimeSeries 返回范围内、截至 `to` 所在 UTC 日的最近 30 个日历日；不补造缺失日期。当前未指定 from/to，避免未经约定把整个统计和列表变成不一致的时间范围。缺少 ingested_at 时展示原因，不制造接入历史。所有 null 指标显示“暂无统计”，无 comparison_period 不展示增长，无 flow.transitions 不绘制执行关系。

## 开发样例

沿用 `.env.local` 的 `VITE_TC_FIXTURES=true` 与 `VITE_TC_FIXTURE_SCENARIO=success|empty|error`，必须在 DEV 显式打开。生产包不包含样例，不在真实请求失败时回退。

统一包仍是 `contracts/training-center/examples.json`，未新增页面统计常量。本次 interceptor 补充 canonical file_detail 所指定文件的详情；generated comparison 返回包内 COMPARISON_NOT_AVAILABLE。其余文件没有详情样例时返回未找到；不从列表补造作者或处理记录。

成功样例可查看 `#/home?catalog=generated` 和 `#/data/txt?catalog=generated`。仅 TXT 无额外筛选的 stats 有标准样例；其他格式统计及未覆盖请求仍走网络，额外统计筛选明确 422。认证仍须真实后端。浏览器测试自身使用受控 HTTP 响应，不改变此行为。

## 验证

执行目录为 `apps/web`：

```powershell
npm run typecheck
npm run lint
npm run build
$env:M0_FIXTURES='false'
npm run test:m0
$env:M0_FIXTURES='true'
npm run test:m0
```

类型检查、Lint、生产构建通过。浏览器回归覆盖：首页数量/版本链接、390px/1440px、图表、服务端分页、搜索、格式缓存隔离、URL 刷新、详情/对比、快照过期和重复刷新、错误不回退、跨版本响应拒绝、对比文本转义，以及原有登录、角色、空间切换、旧页面和下载客户端回归。

最终完整运行：fixtures=false 为 **16 passed / 2 skipped**，fixtures=true 为 **11 passed / 7 skipped**；跳过项是各模式专属场景，未发生失败。生产 dist 的 9 个 JS 文件未检出 interceptor、canonical revision 或处理样例 ID。`git diff --check` 通过。

测试使用独立 5187/5188 Vite 与本机 Chrome；认证和业务 HTTP 由 Playwright 提供，未连接真实业务后端或写共享数据库。截图由完整测试输出到 `apps/web/test-results/m0/home-explorer-*/`；单独视觉复核输出到 `apps/web/test-results/m1-visual/`，已人工查看桌面首页及桌面/移动数据台。

构建仍有一个体积提示：懒加载统计图表 chunk 约 589 kB（gzip 201 kB）；首页不会加载该 chunk。未升级 Ant Design 主版本。兼容方案依据 [Ant Design 官方 React 19 说明](https://5x-ant-design.antgroup.com/docs/react/v5-for-19)。

## 待协作与明确限制

1. Agent 2：实现并提供上述真实只读路由，特别是 all/other stats、筛选与分页同 scope、文件详情和 version_id 映射。确认 stats 未给 from/to 时返回趋势的范围；当前前端取响应末尾 30 日，未对全量指标增加时间过滤。
2. Agent 2＋3：FileDetail 只有处理 run 引用，没有文件到默认 record/step 的映射。批次可能包含多个文件，不能把任意批次记录当作当前文件的对比。当前 workspace 须由可靠片段入口携带 record_id；否则说明需先选择记录。若希望文件行“一键对比”，请提供文件限定的比较入口或兼容新增的默认记录引用，再由 Agent 1 统一更新契约。
3. Agent 3：确认 processing summary/comparison 能消费与 workspace 文件统计相同的 revision，返回同范围快照；如果 C 有独立版本语义，需先明确转换约定，不能绕过范围检查。接入页复用 ComparisonView 时负责请求、角色与 scope 校验。
4. Agent 4：独立复核首页/格式台与生成数据的真实一致性、权限隔离、图中往返 file/record 链接；执行 M2 的真实后端回归。本次作者自己的浏览器测试不替代独立验收。

真实文件上传、Worker 清洗、持久化处理历史、真实 API 全链路和跨模块 M2 验收：本轮未运行。接入/数据集/血缘业务仍由各自 agent 交付，本分支没有代写。
