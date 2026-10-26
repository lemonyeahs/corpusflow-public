# 训练数据中心 M0 收尾验收

日期：2026-10-27。身份：用户授权的集成负责人，可处理公共契约和跨模块兼容修复、提交并正常推送 main。

## 结论与基线

M0 共同骨架与接口设计基线完成，契约版本 `1.0.0`。它满足可登录、hash 深链接、共用类型与样例的 M0 门槛；M1–M3 的业务页面、HTTP 目录查询、真实处理记录/图适配和导出仍需后续交付。

收尾前 main/origin/main：`2a787a8c1734a270be30a4c256d52c06985f08f1`。工作区最初干净，无 merge/rebase。先获取远程并快进同步，保留备份分支 `codex/backup-main-pre-m0-closeout-20261027`，未删除开发分支或 worktree。

本轮没有重复合并已有开发提交，沿用 main 已包含的交付：

| 开发线 | 已在基线中的交付 |
|---|---|
| Agent 1 | `8e42e561e1b16bd76437373c37e8ea176fefc414`，页面壳和公共前端 |
| Agent 2 | `3afb47f9fe93da366399be9eae0a85c7a822833a`，生成器和可重放响应提案 |
| Agent 3 | `8508926`，文本解析首批和处理记录需求 |
| Agent 4 | `bd3b16a`，图遍历与验收首批 |
| Agent 3/4 集成修复 | `aea1b12`、`eca0301`，Windows fixture UTF-8 与类型修正 |

本报告随收尾提交发布；该提交是四个 agent 下一轮应同步的共同基线。提交号和 origin/main 核对结果由最终交付消息记录，避免在提交内容中自引用尚未产生的 hash。

## 修改范围

- 后端共享契约：Pydantic 是唯一 wire 类型来源；严格响应校验和可用于 FastAPI 的 Query 模型。补齐概览、活动、文件详情、manifest 包装、分页、处理摘要/对比、图和错误结构。TypeScript 与独立设计 OpenAPI 自动生成，后端未注册返回样例的假接口。
- 统一样例：B 固定种子 23/11/7、全空响应和 provenance；C 明确 synthetic 的处理/对比与四种 UTF-8 下载格式期望；D 生成来源/文件图与截断。原提案保留作为可重放输入。浏览器消费同一个包，完整分页先筛选再切页，错误结构保留 request_id。
- 冻结决定：destination_counts 为 split 去向；计数单位和 nullable；整体 pipeline_run 引用与步骤 operator_run 区分；快照900秒、每空间10份；生成版本保留当前/前一版；读取/导出100000条及100MiB上限。具体实现责任和 M1 边界写入契约第9节。
- 公共兼容：db/授权依赖稳定导入入口；新错误码不再被改写；目录、TTL、容量配置与可选只读 Compose 挂载。未改变共享服务或现有数据库模型/迁移。
- Windows：沿用上游图 fixture 的显式 UTF-8；补齐 OpenAPI 导出/读取、验证日志/报告编码和子进程 UTF-8。新生成器输出固定 UTF-8/LF，来源哈希按规范 LF 计算，避免 checkout 换行造成漂移。
- 验收：增加契约语义/请求参数检查、共享样例浏览器边界、独立 PostgreSQL+API 的真实认证验证脚本；隔离 Playwright 输出目录，避免并行检查相互删除 trace。

没有合并冲突。语义收口依据原契约和开发者建议，没有用整份文件覆盖解决冲突，没有无关重构或新依赖。

## 实际验证

环境：Windows、Python 3.12.10、本 worktree `.venv`、Node 24.15.0、本机 Chrome、Docker Desktop。本次后端 pytest 直接使用默认 Windows 编码启动，没有依赖全局 `-X utf8` 掩盖文件读取问题。

| 检查 | 最终结果 |
|---|---|
| `python scripts/export_training_center_contract.py --check` | PASS；TypeScript、设计 OpenAPI 无漂移 |
| `python scripts/build_training_center_examples.py --check` | PASS；来源和规范响应可重放 |
| `pytest tests/contract/test_training_center_baseline.py -q` | 71 passed；覆盖请求/响应、OpenAPI 模型及所有引用、计数、快照、图端点、日期、下载、FastAPI Query 字符串解码 |
| `pytest -m 'not integration' -q` | 256 passed，15 integration deselected |
| `ruff check .` / `ruff format --check .` / `mypy` | PASS；157 个 Python 文件格式、61 个源文件类型检查 |
| `python scripts/verify_training_center.py` | 4 个图 fixture 场景 PASS；图 live API 明确 NOT RUN |
| Web typecheck / lint / build | PASS；入口约604.91kB，仍有既存体积提示 |
| 生产样例剔除 | 显式 `VITE_TC_FIXTURES=true` 生产构建后，检查 dist 全部文件字节，未包含统一样例 ID、provenance 或拦截器标识 |
| M0 壳浏览器，样例关闭 | 9 passed；1 个仅适用于显式样例的测试按条件跳过 |
| M0 壳＋B/C/D 边界，success | 10 passed |
| empty / error 请求边界 | 各1 passed |
| `python scripts/verify_training_center_m0.py` | 3 项真实后端浏览器测试通过；新 PostgreSQL 迁移至0022、独立 API `/health` 200、完成后停止自己的服务 |
| `git diff --check` | PASS |

真实验收报告：本机忽略目录 `.local/cf-m0-ddd9b7dd8256/result.json`，对应 `live-browser.log`。测试容器同名，已停止并保留，不影响共享栈。真实验证包含登录→深链→刷新→旧资产空列表→退出、服务端 viewer 覆盖本地伪造 admin、跨空间403、切换空间重新校验、无权限空间阻止进入，以及真实404不回退样例。

首轮静态检查发现并修复新增测试的 nullable 访问和导入排序；首次并行浏览器检查有一次 trace 文件冲突失败，隔离输出目录后重跑两种模式全部通过。未将这些失败标记成通过。

## 独立复核

按 AGENTS.md 要求由另一个只读 reviewer 复核当前差异。复核发现并修复：Query DTO strict 导致合法 HTTP 数字字符串422；样例缺 version/root 必填参数、截断请求元数据；数量指标接受负数/小数；仅正则匹配的 UTC 日期未验证真实日期。每项均补回归。reviewer 独立执行两个生成检查和71项契约测试后确认无剩余阻断问题。其额外建议“清理失败仍写报告”也已纳入验证脚本。

## 未运行及下一轮边界

- 本次未在本地重跑完整源代码 Docker 构建、MinIO/Redis `/ready`、Worker 作业、全部15项集成测试或原构建/审核/发布全流程；仅在本次新数据库执行到 head 的迁移及真实认证所需读写。
- 新业务路由、快照缓存/淘汰、文件查询适配器、处理摘要持久化、导出序列化器、图数据库适配、新功能页面属于 M1/M2，尚未因本次契约冻结变为可用功能。
- 此处是开发身份认证验收，沿用现有 `/auth/session`；不代表新增了生产身份提供方或改变既有认证策略。
- 保留现有 Starlette/httpx 和 SQLAlchemy utcnow 弃用提示；不在本轮升级依赖或重构历史代码。
- 远程 CI 只能在推送后运行，推送后核对当前提交的结果；不能用过去提交的绿灯替代本次检查。

Agent 2/3/4 同步本次收尾提交，按 `docs/plans/TRAINING_CENTER_M0_INTEGRATION.md` 第10节接入；所有新页面继续通过各自目录的默认 index.tsx 挂载，无需编辑 App.tsx。后续有破坏性字段变化必须提升契约版本、再生成并重放样例。
