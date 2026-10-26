# Agent 1：M0 公共骨架交付记录

日期：2026-10-27。工作区：`corpusflow-shell`。分支：`feat/tc-shell-explorer`。起始提交：`263821e`，开工时工作区干净。

## 修改范围

- `apps/web/src/app/`：HashRouter 路由、登录回跳、服务端身份/活跃工作空间核验、角色限制、空间切换、QueryClient 生命周期、查询键、快照辅助函数、响应式外壳、五个模块挂载入口、旧页适配。
- `apps/web/src/ui/`、`styles.css`：公共组件、浅色主题；旧 CSS 选择器限定 `.legacy-page`，旧业务页面文件未改动。
- `src/contracts/training-center.ts`：人工维护的前端草案 DTO；保留未知字段，未宣称后端契约已冻结。
- `src/dev/training-center/`：可追溯手工样例、success/empty/error 显式场景，生产禁用，无失败回退。
- `src/api/`：JSON 错误解析修正、显式样例入口、独立 Blob/Content-Disposition 下载客户端。
- 包清单/锁文件、Vite 代理配置、环境变量样例、M0 浏览器配置与类型检查、README 和模块接入说明。

未实现完整首页、解析/清洗、数据生成或图业务；未修改 API、Worker、模型/迁移，未操作共享数据库或重启共享服务。原 5173 服务未触碰，测试使用独立 5187/5188。

## 接口变化

后端 HTTP 接口未改变。前端新增 `useWorkspaceContext`、`trainingKeys`、`useCatalogScope`、公共 UI 和下载函数；认证复用现有 `/auth/session`、`/auth/me`、`/workspaces`。`request<T>` 遇非 JSON 响应明确抛出 `INVALID_RESPONSE`。模块接入和待确认字段见 [M0 接入说明](../plans/TRAINING_CENTER_M0_INTEGRATION.md)。

## 实际验证

环境：Windows、Node 24.15.0、npm 11.12.1、本机 Chrome，当前 worktree 的独立 node_modules。

| 检查 | 实际结果 |
|---|---|
| `npm --prefix apps/web run typecheck` | 通过；包含应用、M0 测试及 Vite/测试配置 |
| `npm --prefix apps/web run lint` | 通过 |
| `npm --prefix apps/web run build` | 通过；见下方包大小提示 |
| `npm --prefix apps/web run test:m0` | 8/8 通过，样例关闭 |
| `M0_FIXTURES=true` 的完整 M0 浏览器检查 | 8/8 通过，显式 success 样例 |
| `M0_SCENARIO=empty` 的请求边界检查 | 1/1 通过 |
| `M0_SCENARIO=error` 的请求边界检查 | 1/1 通过 |
| `VITE_TC_FIXTURES=true` 生产构建与 dist 内容检查 | 构建通过，未包含样例 revision/workspace/错误码/来源标识，未产生 interceptor chunk |
| `git diff --check` | 通过 |
| 桌面 1440px / 移动 390px 截图 | 已查看；无横向溢出，移动抽屉导航可用，新旧主题隔离 |

浏览器检查覆盖登录保持深链接和过滤参数、刷新/前进/后退、退出、全部新入口和无效路径、服务端角色覆盖本地角色、认证失败、切换空间、九个旧入口、样式隔离、移动导航、查询键范围隔离、下载字节和 UTF-8 文件名、真实错误不回退样例。旧入口访问中既有成功空资产响应，也有明确 503 错误响应；不是完整旧业务验收。

所有 M0 浏览器测试使用 Playwright 提供的认证/业务响应，不是真实 API 登录。检查时约定后端端口 58000/58080 没有监听；未运行真实后端登录、上传/构建/审核/发布/下载全流程或后端测试，没有创建测试业务数据。独立复核需由人工或 Agent 4 完成。

## 已知问题与后续依赖

- 生产入口包约 605 kB（gzip 194 kB），Vite 提示超过 500 kB；构建成功。旧页面已单独懒加载，图表/血缘依赖尚未进入空壳包。
- 旧 `DatasetPage` 的 `product_type` 初始参数尚未适配，由 Agent 2 完成；原构建页默认用法保留。
- 后端 Pydantic/OpenAPI、新接口包装及业务样例仍待 B/C/D 确认，不能将草案当作已实现接口。
- 原全流程 Playwright 的默认落点和 button 导航选择器需 Agent 4 更新至新首页/高级入口。
- Agent 2 补齐概览/样本/manifest、快照策略和构建适配；Agent 3 补齐摘要/对比/导出协议；Agent 4 补齐图响应/截断语义并独立复核。

本轮只提交当前工作分支；未推送、未合并 main。
