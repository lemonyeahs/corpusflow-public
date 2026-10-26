# 训练数据中心 M1 收尾与跨模块联调

日期：2026-10-27。执行人：集成负责人。用户授权直接处理跨模块兼容修复、隔离验收、提交及推送 main；不修复 CI，只验收正常桌面浏览器，不开展小窗口适配。

## 基线与范围

- 开始提交：`7804094a29a7ed24331c1afabb65bb5ada369bb7`，本地 main 与 origin/main 一致。
- 本地备份：`codex/backup-main-pre-closeout-20261027-7804094`。
- Agent 1 的 `4a7d63d`、`c2ee815` 和 Agent 2 的 `711eb5b` 已在基线历史中；处理/图的交付也已集成。本轮不重复 merge 或 cherry-pick，无 Git 合并冲突。
- 本报告替代历史交接中“workspace 不可用”“处理 router 不可注册”“图使用独立快照”的当前状态说明，历史报告保留其当时的执行事实。

## 完成的功能与兼容修复

1. 目录、处理摘要、记录对比、导出和图共用 workspace 冻结投影。在同一 PostgreSQL REPEATABLE READ 事务读取；900 秒不续期、每工作空间合计最多 10 份，过期统一返回 `409 SNAPSHOT_EXPIRED`，每次请求先重新检查成员权限。
2. 注册处理 router，同步实际 OpenAPI、设计 OpenAPI 和生成 DTO。文件对比只选当前文件及实际运行的持久化记录映射，校验内容哈希、输入输出引用和归属；不把最终片段伪装为每一步的结果。logical record key 与 Segment 实体 ID 分开校验。
3. 导出固定到同一快照，只接受成功且输出证据完整的运行；条数和字节超限在成功响应头发出前拒绝。JSONL、Markdown、CSV、TXT 均按 UTF-8 输出，带下载文件名与 revision。
4. 处理步骤持久化实际执行序号；修复“解析已成功、下游失败后重试却直接把整条运行标成功”的问题，保留原成功解析证据和失败尝试，重试真实重跑处理链。
5. 前端跨首页、文件、图、处理页保留统一 scope；处理页恢复 run_id、完成后固定 revision、支持整体刷新、文件对比及下载。generated 目录仍保留生成事实，不产生虚构处理历史。
6. 打通旧构建审核发布：独立审核员可加载已有 Build ID、读取真实来源片段及哈希，显式确认来源质量后审核。默认不自动修改来源质量，仍禁止自审；未确认来源时质量门禁继续阻止发布。CPT、SFT、DPO 均经过真实审核、验证和发布流程。
   完整样本与来源长文本在审核卡片内换行，桌面窗口无横向溢出；截图复核覆盖实际内容，不能只凭点击成功判定布局正常。
7. Windows 验收进程显式启用 UTF-8。在真实 Windows API 进程观察到 CPython/Pydantic 通用 deepcopy 访问冲突后，将快照复制改为显式 DTO 重建及容器复制，保留缓存隔离；4300 条记录连续读取 100 次通过。该修复避开已观察到的崩溃路径，不声称修复 Python 运行时本身。

新增迁移 `0024_execution_sequence` 仅增加 nullable 字段；历史运行不伪造执行序号，按已保存时间确定展示顺序。本次仅迁移隔离数据库，实际部署需正常执行 `alembic upgrade head`，再启动新版 API/Worker。

## 验收方式与结果

验收使用独立、随机名称的 PostgreSQL、S3 兼容存储、Redis、本地 API、Celery solo Worker 和 outbox dispatcher。服务只绑定本地地址，队列与存储隔离；未重启、迁移或清理共享环境。每轮结束停止本轮创建的服务，保留报告与测试资源。

| 检查 | 实际结果 |
|---|---|
| `pytest tests/unit tests/contract -q -m "not integration"` | 422 passed；包含快照隔离、权限撤销、过期、错误导出、真实记录映射、Worker 重试与公开路由门禁 |
| `ruff check .` / `ruff format --check .` | 通过，186 个 Python 文件格式符合要求 |
| `mypy` | 77 个源文件通过；遵循仓库原配置，business.py 原有排除不变 |
| `export_training_center_contract.py --check` / `build_training_center_examples.py --check` | 通过；实际 OpenAPI 漂移由契约测试校验 |
| 前端 typecheck / lint / build | 通过；StatisticsCharts chunk 约 589 kB 的现有构建提示仍存在 |
| 关闭显式样例的桌面受控响应测试 | 28 passed、2 个模式不适用跳过；用于前端异常/交互验证，不代替真实 API |
| 显式样例模式桌面测试 | 10 passed、20 个模式不适用跳过；排除了 mobile/responsive 场景 |
| 默认规模缓存复制压力检查 | 4300 条生成记录连续读取 100 次；修改返回 DTO 不影响缓存 |
| `python scripts/verify_training_center_m0.py --full` | 通过：95 项目录 HTTP 检查、162 项处理/构建 HTTP 检查、14 项真实桌面浏览器测试 |

真实流程覆盖八类格式 txt/md/html/pdf/docx/csv/json/jsonl 上传、对象存储、消息分发、真实解析/清洗/去重/质量步骤、持久化证据、四种格式下载、三类数据集构建审核发布、manifest 与过滤下载，以及旧快照在发布后保持不变。桌面 Chrome 关闭开发样例，不拦截业务请求；覆盖真实登录/授权、4300 条 generated 目录、workspace 目录/图、跨模块固定 revision、独立审核操作及浏览器直接上传到 Worker 下载。

SFT 使用仓库现有非 LLM 构建流程；DPO 使用显式编写的偏好测试记录，再由不同身份标注与审核。没有调用外部模型，也不将这些测试记录宣称为模型生成。

## 失败记录与边界

- 早期真实验收暴露来源未审核导致发布受阻、前端错误地把 logical record key 当作 Segment ID 等问题，已修复并复验。
- `cf-m1-71e8d1c16e1f` 的 API 进程以 Windows 访问冲突退出，faulthandler 指向通用 deepcopy；该轮失败。快照显式复制后重新验收。
- `cf-m1-4201b6cf8cff` 后端通过，浏览器 13 passed / 1 failed：审核断言误依赖随机候选记录顺序。已改为读取该候选实际 evidence 文本进行核对，不放宽内容检查。
- CI/GitHub Actions、移动端/小窗口、外部 LLM、完整旧业务 PostgreSQL integration 套件和人工独立复核未运行。单元回归及本次真实旧构建链不能代表所有历史集成场景。
- 快照当前为单 API 进程内共享存储；多进程/多实例部署前需实现共享持久快照。重启后旧 revision 按过期处理，不自动拼接新旧数据。
- 开发与验收由同一集成人完成；独立审核身份的自动化测试不是人工/另一个 agent 的独立代码复核。本报告不宣称 M3 人工独立验收完成。

## 最终真实运行记录

最终通过轮次：`.local/cf-m1-37be44c2c518/result.json`，`status=passed`，API 在清理前仍正常运行，专用 Redis/S3/PostgreSQL 均成功停止。

- `live-catalog-api.log`：95 次真实目录 HTTP 请求。
- `full-pipeline-api.log`：162 次真实处理/构建 HTTP 请求，八类格式及三类发布全部完成。请求数含状态轮询，随运行速度变化，不等同于独立测试用例数。
- `live-browser.log`：14 passed，57.5 秒；包括桌面审核页无横向溢出断言。
- `browser/` 保存该轮桌面截图；已查看真实清洗对比、上传处理、来源审核截图，审核页视口为 1280×720，无卡片或长文本越界。
- 前一轮 `cf-m1-5820925ad126` 也通过 95 + 138 次 HTTP、14 项浏览器；截图复核发现审核长文本越界后，增加样式修复与断言，以本次最终轮次为准。

回归日志：`.local/closeout-regression.log`、`.local/closeout-browser-mocks.log`、`.local/closeout-browser-fixtures.log`。本地日志、截图、生成目录和数据库资源不进入 Git；脚本、测试、契约和本报告提交，便于在独立环境重放。
