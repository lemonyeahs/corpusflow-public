# Agent 3 / 4 远程代码接入记录

目标分支：`feat/tc-shell-explorer`。合入前：`8e42e56`。

用户授权合并协作方远程代码。拉取后确认 `origin/main` 已包含 Agent 1/2 的共同基线和以下提交：

- Agent 3：`8508926`，文本/Markdown 解析器、Worker 选择逻辑、定向测试、处理执行记录需求。
- Agent 4：`bd3b16a`，多跳图遍历服务、fixture、单元/契约检查及验收脚本。
- 远程集成版本：`ef7456369a9dd72e2d93e496fa35345722b1336a`。

本次通过 `git merge --ff-only origin/main` 将当前工作分支快进到完整远程集成版本，无冲突，不重复 cherry-pick。未修改本地 main，未推送。

## 集成修正

首次检查发现血缘 fixture 在 Windows 默认 GBK 编码下无法读取，导致 17 项测试及验收脚本失败。将脚本和两处测试读取改为显式 UTF-8。

图服务另有 4 处 mypy 错误：校验后的 direction 未收窄到 Literal、重复读取 detail 不能收窄类型、节点/边循环复用变量产生类型冲突。修正类型表达，不改变遍历行为。对 Agent 3 新增的两段条件表达式执行项目规定的 Ruff 格式化。

上述跨模块改动属于本次集成修复，未扩展解析、图查询或 HTTP 业务范围。

## 实际验证

环境：当前 worktree 独立 `.venv`，Python 3.12.10；已有独立 node_modules，Node 24.15.0；本机 Chrome。

| 检查 | 结果 |
|---|---|
| `uv run --frozen pytest tests/unit/test_training_processing.py tests/unit/test_lineage_graph.py tests/contract/test_lineage_contract.py tests/unit/training_center -q` | 81 passed |
| `uv run --frozen python scripts/verify_training_center.py` | 4 个 fixture 场景 PASS；live API 明确 NOT RUN |
| `uv run --frozen mypy apps/api/src/corpusflow/adapters/parser/text.py apps/api/src/corpusflow/modules/lineage_graph apps/api/src/corpusflow/worker/tasks.py` | 4 个源文件通过 |
| Ruff check / format --check（文本解析器、Worker、图服务、相关测试与脚本） | 通过；8 个文件格式符合要求 |
| `npm --prefix apps/web run typecheck` | 通过 |
| `npm --prefix apps/web run lint` | 通过 |
| `npm --prefix apps/web run build` | 通过；保留约 605 kB 入口包大小提示 |
| `npm --prefix apps/web run test:m0` | 9 passed；测试响应验证前端壳 |
| `git diff --check` | 通过 |

未运行真实后端端到端、共享数据库迁移或 Worker 作业；未重启共享服务。远程附带的 `0022` 数据库迁移代码已经同步，但本次没有执行。

## 接口与后续协作

本次修正没有 HTTP/DTO 变化。远程集成基线已包含错误包裹结构、趋势可空等共享 DTO 修正，沿用 `TRAINING_CENTER_M0_MERGE.md` 及模块接入说明。

Agent 3 当前交付是文本解析首批，不包含全部格式、处理摘要/对比/导出 API 或新接入页面。Agent 4 当前交付是图算法和验收首批，尚未提供 `/lineage/graph` HTTP 路由、真实工作空间数据适配或新血缘页面。请两方继续按任务书交付，并在下一次同步时纳入本轮编码/类型修正，避免重复恢复旧版本。
