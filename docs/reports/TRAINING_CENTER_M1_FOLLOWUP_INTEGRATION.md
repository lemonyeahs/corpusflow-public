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

## Agent 1/2 集成验证（远程更新前）

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

该阶段报告目录：`.local/cf-m1-a6aca74aa2da/`，`result.json` 为 passed，`catalog-http.json` 记录89次请求，`live-browser.log` 为9 passed。两台本轮容器停止检查退出码均为0。截图在 `apps/web/test-results/m0-live/`（不提交）；MinIO 镜像 ID 为 `sha256:e5bafea98bd5af4b2cd3e9dba62b02a0a8892182c0244be1494a6cb987eb70ea`。此前失败轮次的报告未覆盖或标记通过。

- generated：实际生成并发布 4300 条、860 文件，检查计数、过滤分页、授权、缺失/损坏/过期与图的现有边界。
- workspace：显式写入 PostgreSQL 的来源、资产、片段、三个已发布版本及每类两条记录，S3 实际保存 manifest；验证固定目录 revision 后修改数据库仍返回旧数据，新 revision 返回更新。
- 下载：CPT/SFT/DPO × JSONL/Markdown/CSV/TXT 共 12 次真实响应，核对中文、UTF-8、文件名、长度、JSONL ID 与 CSV 行数；撤销 training 授权即时403，篡改 manifest 返回409。
- 这些 workspace 数据是带明确 provenance 的验收记录，**没有通过 Worker 或实际发布门禁产生**。读取与下载通过不能替代上传、处理、审核和发布全流程验收。

## 推送前远程更新及兼容修复

首次本地修复提交为 `f8e3c09018f50fe6586109f3b54938c9a82dc13d`。推送前 fetch 发现远程 main 前进到 `291872e8ee174f3fed73a154f413a052e1620e43`，包含 Agent 3 的 `1b3bb04` 与 Agent 4 的 `12e3ce0` 等处理证据/血缘交付。未执行覆盖推送；通过 `a1e918e393eeb1b3dc77dddb9f37917f29569fd6` 正常 merge 保留远程历史。

冲突仅两处：`catalog.spec.ts` 合并双方的 workspace 数据集与 generated 图上下文字段；`verify_training_center_m0.py` 保留双方真实检查并更新未运行列表。没有整份覆盖。

独立审查和复验发现并修复：

- generated 图按 `(dataset_id, dataset_version)` 查找 `DatasetSummary.version_id`，不能把版本字符串 `1` 当成实体 ID。发布目录测试检查三类样本下游与版本上游，真实 HTTP/浏览器再验证样本→版本→样本详情。
- workspace 图内换根保留图快照，跳往文件/数据集页丢弃独立图 token 并带 scope_reset；样本链接补 `tab=samples`。旧处理页不消费 run_id，链接明确为通用“处理工具”，不声称能定位某次运行。
- 重启处理链从 source_version 开始时，每个已执行节点使用新 attempt；复用返工入口预分配的 pending attempt，保留旧记录映射，避免唯一约束冲突和跳过步骤后丢失派生输入。正常过滤是成功执行，保留 filtered_count，恢复 succeeded 状态以兼容既有返工审核门禁。
- 上游 TXT 序列化改为 ID 与角色/优选标签，符合契约；目录测试改为逐项核对结构内容和顺序，JSONL/CSV 仍做结构化重读。对上游本轮四个文件运行格式化，未修改 CI。

新增迁移 `0023_processing_evidence` 只在本轮隔离数据库验证；没有迁移共享开发数据库。processing router 仍不注册：统一 Scope、Query/响应声明及严格完成状态等条件仍待交付。

最终合并结果复验：

| 检查 | 结果 |
|---|---|
| 全仓非 integration 测试 | 414 passed，15 deselected |
| Ruff / format / Mypy | 全部通过，180 个 Python 文件、74 个类型源文件 |
| 契约、样例漂移及实际 OpenAPI 快照 | 通过 |
| 前端 typecheck / lint / build | 通过，保留图表 chunk 体积提示 |
| 上游浏览器回归 | 7项通过；修复两条节点导航场景后2项定向复验通过 |
| 图 API 单元/HTTP | 16项通过，含真实发布目录的版本关联断言 |
| 隔离 PostgreSQL/S3/API | 95次HTTP请求通过，迁移至0023，三类四格式下载正常 |
| 隔离真实浏览器 | 10项通过，含generated样本图→实际样本详情与workspace目录下载 |
| 处理重试定向检查 | 最后日志 attempt 调整后7项通过；Ruff/格式及严格类型检查通过 |
| 独立 PostgreSQL 重试验证 | 通过；新attempt读取本次派生输出，旧partial映射不变、无唯一约束冲突 |

最终隔离报告：`.local/cf-m1-9baf69485b2b/`。本轮 API 与两台容器已按脚本停止，报告保留；实际 Worker 队列执行不在该验证范围内。

重试专项报告：`.local/cf-retry-04e6f5c6909f/summary.json`。独立 PostgreSQL 迁移至0023，验证下游失败后的重试、旧映射保留及正确输入；本次容器已停止并保留。该项对象存储写入使用 stub，只证明数据库事务/重试语义，不表示 Worker、Redis 或上传处理全链路通过。

## 未完成项与下一位负责人

- **Agent 2**：唯一 workspace 快照发行方/存储、统一冻结投影。已有目录适配器已交付，但不能继续等待 Agent 1 编写该服务。保持900秒、不续期、每空间总计10份；整合目录、处理与图在同一一致性边界的投影。
- **Agent 3**：真实步骤 attempt/输入输出/前后记录、摘要和处理导出预检，消费 Agent 2 的统一快照。合格前不注册 processing router；文件比较无真实证据仍404。
- **Agent 4**：图接统一 provider，验证跨模块快照、真实处理血缘和旧流程；其血缘实现另由人工或其他 agent 独立复核。
- **Agent 1 / 集成人员**：上述交付通过审查后接应用入口、处理 router、OpenAPI 与跨页导航。

未运行：Celery Worker/Redis readiness/完整 `/ready`、上传→解析清洗→旧 CPT/SFT/DPO 构建审核发布、真实处理摘要/对比/处理导出、跨模块统一快照与多进程缓存。本轮没有把这些标记为通过。
