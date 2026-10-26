# 训练数据中心 M0 公共骨架接入说明

负责人：Agent 1（A＋E）。分支：`feat/tc-shell-explorer`。基线：`263821e`。

本轮交付前端公共骨架，不代表首页统计、接入处理、数据集查询或图 API 已实现。共享契约仍为 `1.0.0-draft`，待 Agent 2/3/4 与人工负责人评审。没有修改后端路由、数据库、Worker、迁移或其他分支。

## 1. 启动和依赖

在自己的 worktree 中执行：

```powershell
cd apps/web
npm ci
Copy-Item .env.example .env.local
# 按自己的后端地址调整 .env.local 中的 API_PROXY_TARGET。
npm run dev -- --port 5187 --strictPort
```

不要重启占用该端口的其他服务，改用空闲端口。Vite 默认代理仍是 `http://127.0.0.1:58000`，现可用 `API_PROXY_TARGET` 覆盖；`VITE_API_BASE_URL` 是包含 `/api/v1` 的浏览器端接口根地址。生产部署仍需配置反向代理。

本阶段统一安装 React Router 7、TanStack Query 5、Ant Design 5、ECharts 6、echarts-for-react 3、React Flow 12、dagre 1，以及 Node 类型（dagre 自带类型）。精确版本以 `package-lock.json` 为准，其他 agent 不修改依赖及锁文件。图表/图组件按模块引入；当前空壳没有加载这些业务库。

## 2. 页面挂载：不改 App.tsx

`src/app/modules.tsx` 只发现下表五个入口，默认导出无必填 props 的 React 组件。入口不存在时使用公共占位；新增入口后 Vite 自动纳入构建并懒加载。入口注册和路由策略仍由 Agent 1 管理，不扫描任意页面路径。

| Agent | 默认出口（相对于 apps/web/src） | 路由 |
|---|---|---|
| 1 | `features/training-home/index.tsx` | `#/home` |
| 1 | `features/data-explorer/index.tsx` | `#/data/:format` |
| 3 | `features/ingestion/index.tsx` | `#/ingest` |
| 2 | `features/training-datasets/index.tsx` | `#/datasets/:kind` |
| 4 | `features/lineage/index.tsx` | `#/lineage` |

```tsx
import { useParams, useSearchParams } from "react-router-dom";
import { useWorkspaceContext } from "../../app/auth";
import { PageHeader, Panel } from "../../ui";

export default function TrainingDatasetsPage() {
  const { kind } = useParams();
  const [params] = useSearchParams();
  const ctx = useWorkspaceContext();
  return <><PageHeader title={`${kind?.toUpperCase()} 训练数据集`} />
    <Panel title="当前版本">{params.get("version") || "请选择版本"} · {ctx.workspaceId}</Panel>
  </>;
}
```

模块内维护 `api.ts`、`queries.ts`、`components/`、CSS Module；不要复制认证逻辑、创建另一套 QueryClient 或添加全局 CSS。新页面已被父路由保护。`format` 和 `kind` 由公共入口校验；筛选、分页、样本、标签页等继续由模块保存在 URL。

`useWorkspaceContext()` 返回与旧 `ApiContext` 兼容的 `token/workspaceId`，另有经服务端校验的 `session`、活跃 `workspaces` 和 `switchWorkspace(id)`。身份核验调用现有 `/auth/me` 和 `/workspaces`；后者筛除非活跃成员。前端角色限制仅是交互保护，后端仍负责每个业务请求授权。

本轮接入页限 admin/engineer，三类只读数据集页面不添加旧构建页的角色门槛；构建/发布仍由原有页面和服务器限制。`#/ingest` 强制 `catalog=workspace`。其他新页面默认 generated；主导航保留当前 catalog/revision，切换工作空间回到首页并丢弃旧实体选择。

## 3. 共享 UI、样式和请求

共享导出 `src/ui/index.tsx`：

| 组件 | 必填/主要 props |
|---|---|
| PageHeader | `title`、可选 `description/actions` |
| Panel | `children`、可选 `title/extra` |
| MetricCard | `title`、`metric: Metric`；null 显示“暂无统计” |
| ChartFrame | `title/measure/unit/children`；图组件自己提供 |
| LoadingState / EmptyState | 可选 `label` / `description` |
| ErrorState | `error`、可选 `onRetry` |
| ExportMenu | `onExport(format)`、可选 `disabled/busy`；不暗示下载已实现 |

新主题作用于 `.training-center-shell`，使用 `--tc-bg/surface/text/muted/border/primary`。旧 `styles.css` 每条选择器限定 `.legacy-page`，登录页面也沿用此作用域。Ant Design 通过 ConfigProvider 设定浅色主题；弹层使用 Ant Design 上下文，不导入全局 reset 样式。

所有 JSON 请求复用 `request<T>(path, ctx, { signal })`，路径相对于 `/api/v1`。共享错误类型仍是 `ApiError`，保留 `code/status/retryable/requestId`。JSON 无法解析会抛出 `INVALID_RESPONSE`，不能把错误对象当作成功数据。默认不自动重试请求。

下载使用 `src/api/download.ts` 的 `download(path, ctx, fallbackFilename, signal)`，返回 `blob/filename/contentType`，再交给 `saveDownload`。支持 UTF-8 Content-Disposition，保留二进制内容与服务端错误；此客户端会在浏览器内缓冲 Blob，大文件限制/流式方案待 B/C 明确。

## 4. DTO、查询范围和快照

前端类型唯一手工维护入口是 `src/contracts/training-center.ts`，不再向旧 `types.ts` 追加训练中心 DTO。包含 Scope、对象引用、分页、指标/分布/流转、文件、三类样本联合、数据集摘要、处理步骤和图。`PRODUCT_TYPE.cpt === 'pretrain'`。

尚未明确的 `OverviewResponse.formats/recent_activities` 保持 `unknown[]`；不伪造内层协议。处理摘要、记录对比与 manifest 完整包装类型等待责任方样例后补齐。现阶段没有新增 Pydantic DTO 或导出 OpenAPI；契约文档不能当作已存在的接口。

查询键必须使用：

```ts
trainingKeys.query(ctx.workspaceId, catalog, revision, "files", {
  format, q, source_kind, language, status, offset, limit,
});
```

键包含 workspace/catalog/revision/resource/filters。身份或空间变化会卸载旧页面、取消查询、清空旧客户端并创建新客户端，避免本地状态及缓存跨空间复用。不要把 token 放入查询键。

`useCatalogScope()` 提供 catalog、revision、pinScope、changeCatalog、refreshSnapshot。先查询入口资源，核验响应范围，用 `pinScope(response.scope)` 将快照写入 URL，再启用关联统计/列表/详情。`pinScope` 拒绝不匹配的工作空间/目录/已固定版本。遇到 `409 SNAPSHOT_EXPIRED`，模块显示错误并通过 `refreshSnapshot()` 清理当前范围查询、移除 revision/offset，重新获取入口快照；关联查询在新 revision 固定前保持禁用。不要用旧页面数据拼接新快照。

## 5. 显式开发样例

`src/dev/training-center/fixtures.ts` 保存手工编写的契约样例及 provenance（来源文件、revision、固定时间、seed=null）。这些不是生成器输出或实际处理记录，没有虚构已完成步骤。等待 B/C/D 提交经审查的响应后由 Agent 1 统一替换。

在自己的 `apps/web/.env.local` 中设置并重启自己的 Vite：

```dotenv
VITE_TC_FIXTURES=true
VITE_TC_FIXTURE_SCENARIO=success
```

场景可选 `success/empty/error`。必须同时满足 Vite DEV 和字符串 `true`；生产构建即使设置 true 也不包含拦截器。拦截发生在网络请求之前，没有失败回退分支。workspace 目录、认证、写入、下载及未覆盖请求始终访问真实 API。

当前覆盖 generated 的概览、文件分页、三种样本分页、单个文件图。样例文件 ID 为 `fixture-file-1`；CPT/SFT/DPO 数据集 ID 分别为 `fixture-dataset-1/2/3`、版本 `v1`。不是任意 ID 都有响应。文件示例未处理、没有接入时间，Tokens 未知；样例图没有执行节点。此最小样例集不能作为业务正确性验收依据。

## 6. 旧页面兼容

高级分组保留 assets、processing、document、datasets、dpo、admin，并额外保留 dashboard、ingest、lineage。旧组件文件没有修改；适配在 `src/app/LegacyPage.tsx` 内完成。

- `#/advanced/assets?format=pdf` 保留格式过滤。
- `#/advanced/document?asset_id=...` 保留文档选择，刷新可恢复。
- `#/advanced/lineage?segment_id=...` 保留资产片段跳转与刷新。
- `#/advanced/datasets` 和 `#/advanced/dpo` 原构建行为保留；`product_type` 初始选择/嵌入标签页仍需 Agent 2 对旧 DatasetPage 做兼容适配，本轮不越权修改。
- 旧页面原本只有内存导航，没有旧 hash 地址需要迁移。旧测试对“总览为登录落点”和 button 导航的定位需要 Agent 4 适配至新首页/高级入口。

## 7. 待确认问题与协作请求

| 责任方 | 明确交付/决策 |
|---|---|
| Agent 2 | overview formats/metrics/activity 的完整字段，DatasetSummary status/record_unit 枚举，统计快照保留与过期策略，分页排序，manifest 和文件详情包装，成功/空/错响应；生成目录配置和挂载需求；旧构建页 product_type 初始值适配 |
| Agent 3 | summary/totals、before/after、record_ref 的准确结构，错误码、下载上限/失败语义、允许部分输出的条件；真实处理样例，不能用前端样例替代历史执行 |
| Agent 4 | 图关系方向映射、节点 detail、截断响应样例及空根节点策略；独立复核本轮壳、授权边界、旧入口和测试覆盖，更新原全流程测试导航 |
| 2＋3＋4 | 向 Agent 1 提交 DTO/公共配置/依赖变更请求；在模块自己的目录开发，不修改 App.tsx/路由/主题/锁文件 |

本轮 M0 范围按用户指令止于公共骨架。后端契约冻结、真实登录与旧业务全流程仍需可用隔离后端和人工/其他 agent 独立复核；后续由人工负责人决定集成及推送，不直接合并 main。

## 8. 验证方式

```powershell
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run build
npm --prefix apps/web run test:m0
$env:M0_FIXTURES='true'
npm --prefix apps/web run test:m0
$env:M0_SCENARIO='empty' # 再以 error 执行同一请求边界检查
npm --prefix apps/web run test:m0 -- --grep 'fixtures require'
```

M0 测试位于 Agent 1 自有 `src/app/__tests__/`，不占用 Agent 4 的 `tests/training-center/`。测试各自启动 5187/5188、禁止复用已有服务，默认使用本机 Chrome；可设置 `M0_BROWSER_CHANNEL=msedge`。测试中的认证与业务请求响应由 Playwright 提供，不写共享数据库。生产样例剔除另以显式开关构建并检查 dist；结果记录见本轮交付报告。

实现参考：[React Router HashRouter](https://reactrouter.com/api/declarative-routers/HashRouter)、[QueryClientProvider](https://tanstack.com/query/latest/docs/framework/react/reference/functions/QueryClientProvider)、[Ant Design 主题](https://ant.design/docs/react/customize-theme/)。

## 9. 2026-10-27 集成修订

Agent 1 的 `8e42e56` 和 Agent 2 的 `3afb47f` 已在集成仓库依次合并。本轮仅接收前端骨架与离线生成器/响应提案，未冻结完整后端契约。独立复核结果见 [集成报告](../reports/TRAINING_CENTER_M0_MERGE.md)。

- `ApiErrorBody` 对齐现有 `core/errors.py`：`request_id` 位于顶层，`error.details` 为对象数组。共享 JSON/下载客户端读取顶层请求 ID，并兼容旧嵌套字段。
- `FormatStatsResponse.ingestion_trend` 允许 `null`，可用 `availability.ingestion_trend` 说明没有真实接入时间；不以空时间序列冒充已知统计。
- `DatasetOverviewResponse.destination_counts` 暂为 `unknown`。Agent 2 建议按 split 返回带单位的桶，原 DTO 曾假定为数值字典，但契约未定义业务含义。没有运行时消费者，本轮不强行选择；接入数据集概览前由 Agent 1/2 确认含义与结构。
- Agent 2 的 `contract_examples/` 仍是独立、可重放的提案，未接到浏览器拦截器或真实 HTTP。前端最小手工样例继续保留自身 provenance；不能把两套样例说成已经统一冻结。
- 生成器新增测试改名为 `test_catalog_generation.py`，避免与已有 `tests/unit/test_generation.py` 冲突。其他 agent 应运行仓库级 pytest 收集，而不只测试自己的子目录。
- P0-I、responsive 测试的登录落点已改为新首页。其余历史端到端测试仍含早于本轮的失效页面/按钮，需 Agent 4 结合当前旧业务流程独立修订，不能仅批量替换导航后声称业务验收通过。
