# M1 目录与数据集后续集成

日期：2026-10-27。集成 Agent 1 的公共 scope 校验与 Agent 2 的 workspace 只读适配、CPT/SFT/DPO 页面及完整过滤导出。本轮不修复 CI，未修改 workflow；不宣称处理链或跨模块统一快照已完成。

## 提交与合并

- 集成前 main / origin/main：`acb7ce0fa31befaa203bf1213ad3eebbc4afaa06`。
- 本地备份：`codex/backup-main-pre-m1-followup-20261027-acb7ce0`，指向上述提交。
- Agent 1：`feat/tc-shell-explorer`，交付 `4a7d63d7b6173d78a1165747ec9594f124a7d266`、`c2ee8155c50be7e889df79c0b08dfde1897057f8`，合并记录 `34bae3c`。
- Agent 2：`feat/tc-catalog-datasets`，交付 `711eb5b53d0f0c1b0c6a1696e6bf76e397ec3cf6`，合并记录 `a8e5cc2`。其祖先 `78a706e` / `0506eb4` 中的 workspace 适配器、页面与序列化器接入一并审查，保留原历史。
- 主仓库开始时为干净 main，无 merge/rebase；两交付 worktree 干净，未替换开发分支。获取远程后本地与 origin/main 一致，无远程同名开发分支。
- 按 Agent 1 → Agent 2 顺序 `merge --no-ff`，无文本冲突，无 cherry-pick。集成兼容修复单独提交，最终基线为包含本报告的提交，以推送核对结果为准。
- 未提交凭据、生成语料、运行日志或本地环境配置；未删除 worktree、开发分支或备份。

## 接入与独立复核

1. `ExportQuery` 兼容新增可空 `q`；路由统一用 Query DTO，未知参数及 offset/limit 仍拒绝。重新生成 TypeScript、设计 OpenAPI 与实际 OpenAPI，默认应用包含 11 个目录 GET；处理 router 保持未注册。
2. 数据集页接入公共 `scopedRequest`，校验 workspace/catalog/revision/as_of/metric_definition_version；出现快照冲突或过期后隐藏旧详情与下载入口，取消下载并整体刷新。
3. 数据集来源/版本跳转血缘复用公共导航。workspace 暂时丢弃独立目录 revision 并带 scope_reset 提示，不能把独立图快照冒充同一时点。
4. 数据库版本成员查询改用同 workspace、受支持产品类型的关联查询，避免大规模 IN 参数列表。实时用途授权按每批最多 1000 资产查询，最终核对完整集合；缺末批授权仍拒绝。
5. 数据集网格允许内容收缩，manifest 保留换行与滚动。导出菜单改为点击打开（同时支持触屏），在启动异步下载前显式关闭，避免悬停和 busy 切换留下弹层。浏览器重试定位兼容 Ant Design 自动插入的中文空格。
6. 后端授权/容量及前端快照分别独立复核；子任务实现的修复由集成人员再次审查。Query/OpenAPI、隔离脚本与导航修复另经只读复核。

## 实际验证

| 检查 | 结果 |
|---|---|
| `pytest -m 'not integration' -q` | 401 passed，15 integration deselected |
| 全仓 Ruff / 格式 / Mypy | 通过，178 个 Python 文件、74 个严格类型源文件 |
| 契约生成与统一样例 `--check` | 均通过，无漂移 |
| 前端 typecheck / lint / build | 通过；图表 chunk 约 589 kB，保留体积提示 |
| 公共浏览器回归，关闭样例 | 28 passed，2 按模式跳过；HTTP 拦截用例，不计真实后端 |
| 公共浏览器回归，显式样例 | 11 passed，19 按模式跳过 |
| 数据集专项浏览器 | 完整运行13 passed；最终点击导出调整后相关3项定向通过；此前两项定位失败已修正 |
| 共享菜单接入页定向回归 | 1 passed，当前运行下载格式与范围保持 |
| 隔离真实 PostgreSQL/S3/HTTP | 89 次请求通过，含12次三类四格式下载 |
| 隔离真实浏览器 | 最终9 passed，涵盖认证、目录、图、三类样本/manifest/下载及390px页面 |
| 生产包样例标记检查 | 未发现 fixture.invalid / m0-example-run / fixture_scope_mismatch |

Windows 子进程、HTTP 报告和生成文件沿用显式 UTF-8。测试中的 SQLAlchemy datetime.utcnow、Starlette/httpx 弃用提示未作为本轮无关重构处理。

真实浏览器复验中，移动端即时宽度断言遇到仍处于桌面位置的导出浮层；后续检查发现异步下载时禁用 Dropdown 会留下菜单，已改为显式控制关闭状态。测试等待菜单隐藏和响应式布局稳定后检查，没有移除宽度断言。另一次认证深链旧断言不允许新增 revision，与上线后的 workspace 固定快照行为冲突；改为逐项校验路径、目录、搜索、分页和非空 revision，并验证刷新保持同一 URL。早期失败结果保留于本地报告，不记为通过。

### 隔离真实服务

运行 `.venv/Scripts/python.exe scripts/verify_training_center_m0.py --catalog`。脚本只连接本机 Docker，为每轮新建唯一名称 PostgreSQL、S3 和随机端口 API；迁移仅运行在本轮数据库。MinIO 使用本地已构建镜像的不可变 ID，不启动或迁移共享服务；结束后停止自己创建的服务，保留本地报告。

最终报告目录：`.local/cf-m1-a6aca74aa2da/`，`result.json` 为 passed，`catalog-http.json` 记录89次请求，`live-browser.log` 为9 passed。两台本轮容器停止检查退出码均为0。截图在 `apps/web/test-results/m0-live/`（不提交）；MinIO 镜像 ID 为 `sha256:e5bafea98bd5af4b2cd3e9dba62b02a0a8892182c0244be1494a6cb987eb70ea`。此前失败轮次的报告未覆盖或标记通过。

- generated：实际生成并发布 4300 条、860 文件，检查计数、过滤分页、授权、缺失/损坏/过期与图的现有边界。
- workspace：显式写入 PostgreSQL 的来源、资产、片段、三个已发布版本及每类两条记录，S3 实际保存 manifest；验证固定目录 revision 后修改数据库仍返回旧数据，新 revision 返回更新。
- 下载：CPT/SFT/DPO × JSONL/Markdown/CSV/TXT 共 12 次真实响应，核对中文、UTF-8、文件名、长度、JSONL ID 与 CSV 行数；撤销 training 授权即时403，篡改 manifest 返回409。
- 这些 workspace 数据是带明确 provenance 的验收记录，**没有通过 Worker 或实际发布门禁产生**。读取与下载通过不能替代上传、处理、审核和发布全流程验收。

## 未完成项与下一位负责人

- **Agent 2**：唯一 workspace 快照发行方/存储、统一冻结投影。已有目录适配器已交付，但不能继续等待 Agent 1 编写该服务。保持900秒、不续期、每空间总计10份；整合目录、处理与图在同一一致性边界的投影。
- **Agent 3**：真实步骤 attempt/输入输出/前后记录、摘要和处理导出预检，消费 Agent 2 的统一快照。合格前不注册 processing router；文件比较无真实证据仍404。
- **Agent 4**：图接统一 provider，验证跨模块快照、真实处理血缘和旧流程；其血缘实现另由人工或其他 agent 独立复核。
- **Agent 1 / 集成人员**：上述交付通过审查后接应用入口、处理 router、OpenAPI 与跨页导航。

未运行：Worker、Redis readiness/完整 `/ready`、上传→解析清洗→旧 CPT/SFT/DPO 构建审核发布、真实处理摘要/对比/处理导出、generated 图、跨模块统一快照与多进程缓存。本轮没有把这些标记为通过。
