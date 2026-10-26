# M1 generated API 与首页、数据台集成

日期：2026-10-27。范围为用户授权的 Agent 2 首批目录 API 与 Agent 1 首页/格式数据台集成，不表示四条开发线的整个 M1 已完成。按用户最新要求，本轮不修复 CI，也未修改 CI workflow。

## 提交与审查

- 集成前 main / origin/main：`58fe070955b3a8c66806dc8f2d8ed2f152d5036d`。
- 集成前备份：`codex/backup-main-pre-m1-catalog-20261027`，指向上述提交。
- Agent 2：`feat/tc-catalog-datasets` / `7e2f227b12f6df6f11689d957e319be06873464e`，merge commit `7df8785`。
- Agent 1：`feat/tc-shell-explorer` / `15efe96`，merge commit `9256ba7174037f7f5e6a43a773d4d1ed7ac11d6f`。
- 两个交付分支均核实存在、交付 worktree 干净、没有远程同名分支。本轮均使用 `--no-ff` merge，无文本冲突，无 cherry-pick。
- 最终集成修复单独提交；精确最终基线以包含本报告的集成提交和推送后 `origin/main` 为准，不在提交内写自身哈希。

交付差异未混入 `.env`、凭据、批量生成数据或运行日志。Agent 1 的依赖补丁及锁文件属于授权的公共文件范围；Agent 2 原交付未修改共享入口。独立审查分别检查前端快照/过滤/对比语义与后端授权/目录完整性，以下后端问题均修复后复核。

## 接入与修复

1. 在默认 `create_app` 注册 9 个训练中心 GET 路由。契约测试不再测试内额外挂载 router，避免测试通过但实际服务没有路由。
2. 从实际应用重新导出 `docs/api/openapi.json`，补齐 Bearer、X-Workspace-ID 和 401/403/404/409/413/422/503 错误响应。设计 DTO、契约版本 `1.0.0` 与统一样例没有字段变更。
3. generated-v1 必须恰好包含 CPT/SFT/DPO 各一份数据集，包括空目录。拒绝多份同类数据覆盖计数字典、掩盖实际记录数的情况。
4. 发布前按读取端相同的索引容量上限检查，超限 413，不写出下一次读取会失败的索引，不改变旧指针。
5. 将有界文件读取改为最多 64 KiB 分块，保留 `maximum+1` 增长检测、逐文件全字节 SHA256、symlink/junction 和路径检查。默认 4300 条目录原实测约 19–20 秒/请求；独立 profiler 定位为每个小文件重复申请近 100 MiB 缓冲。修复后真实 HTTP 暖读取约 0.5 秒（当前 Windows 环境观测，非性能 SLA）。
6. 工作空间适配器未接入时仍返回 503 / ADAPTER_UNAVAILABLE，用户提示改为“当前数据适配器暂不可用”，避免误报路径不存在。前端保留真实错误，不回退样例。
7. 扩展隔离验收脚本 `verify_training_center_m0.py --catalog` 和真实网络/browser 用例；Windows 子进程及报告显式 UTF-8。原无参数 M0 认证验证入口保留。

## 验证结果

| 检查 | 结果 |
|---|---|
| 全仓 `pytest -m 'not integration' -q` | 340 passed，15 integration deselected |
| 全仓 ruff / format / mypy | 通过；164 个 Python 文件，64 个 mypy 源文件 |
| 设计契约与统一样例 `--check` | 均通过，无漂移 |
| 前端 typecheck / lint / build | 均通过，包含真实浏览器测试的类型检查 |
| 浏览器回归，关闭样例（HTTP 拦截测试） | 16 passed / 2 mode-specific skipped |
| 浏览器回归，开启显式样例 | 11 passed / 7 mode-specific skipped |
| 显式 `VITE_TC_FIXTURES=true` 生产构建 | 通过；16 个产物无统一样例 revision/workspace、处理样例标识或 interceptor |
| 独立后端修复复验 | 数据集结构 2 项通过；分块读取与索引上限 8 项通过 |
| 真实 HTTP / 浏览器 | 52 次请求通过；5 项真实浏览器用例全部通过 |

真实联调使用新建、随机命名的本地 PostgreSQL 16 容器、独立端口 uvicorn、独立工作空间及 `.local/cf-m1-*` 目录，运行已有迁移，不修改模型或迁移。Redis/对象存储指向不可用测试端口，LLM 禁用。没有迁移或重启共享开发服务。

真实 HTTP 矩阵共 52 次网络请求，验证默认 4300 条/860 个文件、9 个路由、DTO、过滤后分页、CPT/SFT/DPO split 和完整 manifest hash；包含未认证、跨空间、成员撤销、禁用用户、无发布目录、固定旧 revision、空目录、退役、暖缓存后篡改及超限。无 MockTransport、依赖覆盖或统一样例替代。

首轮联调因发现读取缓冲性能问题主动中断；修复后 HTTP 通过。首轮浏览器 4 通过/1 失败，暴露适配器错误提示不准确及测试错误地查找机器码；已修正提示，并使测试同时验证 HTTP 错误码和用户可见中文文案。第二轮因测试点击隐藏 radio 输入失败，改为点击可见标签。最终 `.local/cf-m1-fc328c44bef5/result.json` 为 passed，52 次 HTTP 和 5 项真实浏览器均通过，本轮 API 与专用容器均已停止。桌面首页、桌面/390px 移动数据台截图已检查；无浏览器 pageerror、无样例响应。

推送前 fetch 发现 origin/main 更新为 `c62b57095588b1015e034b17233daef0c3a96448`，含 Agent 3/4 处理、接入和图功能。先保存以上已验证集成结果，再正常合并远程更新并补验；不覆盖他人提交。

## 保留限制与未运行项

- 15 项已有 integration 测试未运行；本轮数据库验证是独立 PostgreSQL 迁移及真实认证/目录 API/browser 联调，不宣称覆盖全部旧业务数据库流程。
- workspace 数据库目录、处理产物、导出、图 API、CPT/SFT/DPO 新页面及旧构建流程完整联调仍属后续交付。无清洗记录时对比返回 COMPARISON_NOT_AVAILABLE；不构造处理历史。
- Worker、Redis/MinIO readiness、真实处理链及完整旧业务回归未运行。
- 保留现有 Starlette/httpx、SQLAlchemy 弃用警告；ECharts 异步 chunk 约 589 kB，有体积警告。入口 chunk 约 367 kB，构建成功。
- 不修复或宣称远程 CI 通过。推送采用普通 fast-forward push；其他 agent 应先同步最终 origin/main，再继续各自功能。
