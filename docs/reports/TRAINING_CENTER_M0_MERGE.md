# 训练数据中心 M0 分支集成记录

日期：2026-10-27（Asia/Shanghai）。身份：用户授权的跨模块集成负责人。工作目录：主仓库 `corpusflow-public`；未修改或删除开发 worktree。

## 基线与合并

- 集成前 `main` / `origin/main`：`263821e6b6014ec99ff3bd816a982f44717f4c55`。
- 开工时工作区干净，没有 merge/rebase 进行状态；fetch 后本地与远程 main 无分叉。
- 保留本地备份：`codex/backup-main-pre-tc-20261027-263821e`，指向上述基线。
- 顺序 1：`feat/tc-shell-explorer`，交付 `8e42e561e1b16bd76437373c37e8ea176fefc414`；merge 提交 `98c2a4635e5d33ae269127290c27dba34f8654d3`。
- 顺序 2：`feat/tc-catalog-datasets`，交付 `3afb47f9fe93da366399be9eae0a85c7a822833a`；merge 提交 `633e3652b8c27f4ec453f4c4e90e2071de5b7e51`。
- 两个交付均为本地分支 tip，远程没有同名开发分支；两次均用 `--no-ff` merge，无文本冲突、未使用 cherry-pick。
- 后续集成修复与本记录一起单独提交；最终提交号及推送后的远程核对结果见交付消息（避免在提交内自引用提交号）。

## 审查范围与修复

Agent 1 的 31 个文件属于前端公共骨架/配置/文档范围；Agent 2 的 11 个文件属于生成器、离线响应提案和测试范围。没有改动数据库模型、迁移、Worker 或旧业务组件实现。提交的 JSON 是有来源配置的分页响应提案，批量生成目录未进入 Git。变更路径与常见凭据签名扫描未发现真实 `.env`、私钥或服务令牌；`.env.example` 是配置说明。

本轮接收的能力是路由壳、认证和工作空间包装、开发样例机制以及标准库生成器；并非完成训练中心业务 HTTP、数据集页面或真实处理链。复核了实际文件归属、引用、来源组切分、生成事实、未知 Tokens/接入时间、空执行历史；旧 CSS 声明块与基线一致，仅选择器作用域改变。锁文件没有在集成安装过程中变更。

集成修复：

1. 新增 `test_generation.py` 与已有同名测试导致全仓 pytest 收集失败。仅将新文件改名为 `test_catalog_generation.py`，测试内容不变。
2. 前端错误 DTO 改为后端现有顶层 `request_id` 和数组 `error.details`，JSON/下载客户端保留顶层请求 ID。新增浏览器回归同时验证错误码、状态、重试标志、请求 ID，以及成功状态下返回 HTML 时抛出 `INVALID_RESPONSE`。
3. 趋势 DTO 允许 `null` 与可选不可用原因，符合没有真实接入时间时不能编造趋势的约定。
4. `destination_counts` 的字典/桶数组及 split/下游用途语义尚未确定，暂用 `unknown` 保留边界。本轮无消费者，不需要合并相互矛盾的业务行为；依赖该字段的页面接入应等待确认。
5. 两个仍直接依赖登录落点的旧测试（P0-I/responsive）改为新首页；未宣称完成历史全流程测试适配。

## 实际检查

环境：Windows、Python 3.12.10、Node 24、项目独立 `.venv` 和当前仓库 `apps/web/node_modules`。Python 依赖使用 `uv sync --frozen --group dev`；前端 npm install 后锁文件不变。浏览器为本机 Chrome，测试只启动自己的 5187/5188 端口、不复用已有服务。未迁移、清理或重启共享环境。

| 检查 | 结果 |
|---|---|
| `npm --prefix apps/web run typecheck` | 通过，包含应用与 M0 测试/配置 |
| `npm --prefix apps/web run lint` | 通过 |
| `VITE_TC_FIXTURES=true` 下 `npm --prefix apps/web run build` | 通过；入口 604.91 kB / gzip 194.35 kB，保留大于 500 kB 提示 |
| dist 的 fixture revision/workspace/错误码/函数/来源标识扫描 | 无匹配；未生成 interceptor chunk |
| `npm --prefix apps/web run test:m0` | 9/9 通过，样例关闭 |
| `M0_FIXTURES=true` 完整 M0 浏览器检查 | 9/9 通过，success 场景 |
| empty / error 场景 `--grep 'fixtures require'` | 各 1/1 通过 |
| 桌面 1440px / 移动 390px 截图复核 | 已查看，无横向溢出；单独重跑移动/桌面场景 1/1 通过以保留截图 |
| `python -m pytest tests/unit/training_center tests/contract -q --basetemp .local/tc-integration/pytest-focused-final` | 52/52 通过：新增 51 项及既有 OpenAPI 快照 |
| `python -m ruff check .` | 全仓通过 |
| `python -m ruff format --check .` | 141 个文件通过 |
| `python -m mypy` | 54 个源文件通过 |
| `python -m pytest -m 'not integration' -q --basetemp .local/tc-integration/pytest-unsandboxed` | **154 通过、1 失败、11 deselected**，不是全绿；历史失败见下文 |
| `git diff --check` | 通过 |

测试启动的环境问题也保留说明：首次 npm ci 因 Windows 原生绑定文件占用/权限返回 EPERM，随后 npm install 成功，但仍提示无法清理旧绑定备份；未停止占用者。首次 uv 下载因沙箱 DNS 失败，获执行权限后成功。首次 focused pytest 因本次指定临时目录的父目录不存在而有 13 项 setup error；创建父目录后最终 52 项通过。首次全仓 pytest 暴露上述重名收集错误，修复后重跑。沙箱内浏览器/完整测试无进展的运行已中止；随后在获准权限下完成，未把中止运行计为通过。

所有 M0 浏览器认证/业务响应均由 Playwright 提供，不是真实后端验收。浏览器检查涵盖登录回跳、刷新/历史、服务端角色、工作空间切换、九个旧入口、样式隔离、移动导航、查询键隔离和下载字节；不能替代真实上传/构建/审核/发布。

## 全仓历史失败复核

唯一执行失败是未修改的 `tests/unit/test_foundation.py::test_originals_preserved`。Windows checkout 的 CRLF 导致根目录两份原型资料的磁盘字节 SHA256 与 LF 基准不同；把 CRLF 还原 LF 后与预期及 `263821e` Git blob 完全一致。此外，测试要求的 `《CorpusFlow 需求分析与确认》.md` 在该 Git 基线中就不存在。

在 `.local/tc-integration/baseline/` 提取 `263821e` 的原测试函数与两份原始 Git blob，独立执行相同校验，前两个哈希通过，第三份缺失文档导致 `FileNotFoundError`。直接加载完整基线测试文件的首次尝试因临时目录无应用配置而无法收集，随后仅提取不依赖应用的原校验函数完成上述复现。未改写历史校验、修改预期哈希、伪造缺失原文或把该失败标成通过。

本次相关检查通过，历史资料缺失与行尾问题不是这两个分支引入的阻断。全仓检查仍需后续恢复原始资料并约定跨平台行尾策略。

## 生成命令复核

在主仓库实际运行 `python scripts/generate_training_center.py --workspace-id tc-integration-20261027 --seed 42`，并分别增加 `--cpt-count 23 --sft-count 11 --dpo-count 7`、`--cpt-count 0 --sft-count 0 --dpo-count 0`。三次退出码均为 0，产物只在 Git 忽略的 `.local/training-center/tc-integration-20261027/` 下。

| 配置 | CPT | SFT | DPO | revision |
|---|---|---|---|---|
| 默认 | 1800/100/100 | 1350/75/75 | 720/40/40 | `966ac798abfe9662f89d9c1f840bb5345d2dd10b491071ad5d64c5a96396fd12` |
| 23/11/7 | 21/1/1 | 10/1/0 | 6/1/0 | `1690b3b8d5efeedf6d9a8fe2eda0e297a1d5ca47f03659c589b83dfa13e63a14` |
| 全空 | 0/0/0 | 0/0/0 | 0/0/0 | `46205d1a629eed7ba3b2d3ec54fac38848e1ae5b4eab07d7f5451d925d447558` |

workspace ID 不同会改变 revision，因此不与开发者 `tc-agent2` 的 revision 直接比较。

## 未运行及后续依赖

- 真实后端登录、完整旧业务端到端、真实 `/ready`、Worker、数据库迁移和三条业务联调线：未运行。本轮没有处理链或数据库变更，也没有建立完整隔离服务栈。非集成单元测试内的 TestClient/readiness 测试通过不表示实际服务已就绪。
- 新 HTTP / Pydantic DTO / 新接口 OpenAPI 验收：未运行，相关实现尚未交付；既有 OpenAPI 快照检查通过。
- Agent 1/2 继续确认版本实体、单位/状态枚举、去向统计含义、快照 TTL/保留、目录配置、认证依赖入口和错误码支持。不会将离线响应自动接到失败的真实请求上。
- Agent 2 完成只读 HTTP 与旧构建页 product_type/嵌入适配；Agent 3 提供序列化器及真实处理记录；Agent 4 更新旧导航回归与图语义，并独立复核后续业务功能。
- 其余历史 E2E 本身还引用基线已无入口的质量/RAG/盲评等按钮以及旧发布页面；本轮不把这些旧测试改造成新的业务实现。
- 公共字段改动为集成负责人跨模块授权范围；共享契约维持草案。其他 agent 以最终推送的 main 提交作为共同基线，不依据某一开发分支单独继续共享接口工作。

## CI 失败后的修正（2026-10-27）

首次推送 `0d07e10` 后，[Actions 40369158630](https://github.com/lemonyeahs/corpusflow-public/actions/runs/40369158630) 的 `checks.log` 确认 ruff、格式、mypy 均通过，pytest 为 154 通过、1 失败；失败正是原始需求文档路径不存在。因此此前“历史失败不是本次阻断”的结论不足以保证 CI 通过，首次集成没有完成远程验证闭环。

进一步核对发现：`202730b` 主动删除了根目录需求文档，但 `docs/specs/CorpusFlow_01_需求分析与确认_V1.0.md` 自初始提交起一直保留，Git blob 的 SHA-256 正好是测试原有预期 `f9065571c0f625cb26712ba1197bcd01ebf327bb1d0d8d2df9ee25bdf207c1a3`。修复将校验路径指向该保留版本，并仅将文本 CRLF 规范为 LF 后计算哈希。三个预期哈希均不变，没有 skip/xfail，也没有恢复已删除的重复文档。

修复后在同一项目依赖环境重跑 CI `make check` 对应的全部命令：ruff 通过，141 个文件格式通过，mypy 54 个源文件通过，非集成 pytest **155 passed、11 deselected**。这些替代上文首次集成的本地失败结论；历史检查记录仍保留。完整远程环境验证结果以修复提交对应的 GitHub Actions 为准。

## 后续迁移验证修正（2026-10-27）

`2fdc7d6` 对应的 [Actions 40370166969](https://github.com/lemonyeahs/corpusflow-public/actions/runs/40370166969) 已通过代码检查、镜像构建及隔离服务启动，随后 `migration-and-storage.log` 报告 7 passed、3 skipped、1 failed。原迁移测试仍硬编码 head 为 `0020_dpo_import_idempotency`，实际已有 `0021_metadata_proposals`。修正为从 Alembic 读取单一 head，同时保留数据库版本和 `command.check` 的实际断言，并在最终 reupgrade 后补充这两项验证。

在本次新建、绑定随机 loopback 端口的 PostgreSQL 16 容器中继续验证后，发现旧断言掩盖的真实模型差异：0021 的五个 JSON 字段应为 PostgreSQL JSONB，两张表的 created_at/updated_at 应为 NOT NULL。新增 `0022_metadata_schema_alignment` 对齐既有模型，不修改已发布的 0021。迁移先检查所有历史时间戳；存在 NULL 时抛出 `LEGACY_TIMESTAMP_MISSING` 并回滚，不填造历史记录。降级还原 0021 的 JSON 与 nullable 结构，JSON 语义内容保留。

实际本地验证：`pytest tests/integration/test_migration.py -q` **5 passed**，覆盖完整 upgrade/downgrade/reupgrade、模型无漂移、已存在嵌套 JSON/中文数组与时间戳保留，以及两表各两时间戳的失败前置检查和回滚。仅使用本次专用容器 `cf-ci-migration-20261027-2fdc7d6` 和随机测试数据库，不连接共享数据库。ruff 全仓通过，142 个文件格式通过，mypy 54 个源文件通过。非集成回归结果及最终远程状态见交付消息。

数据库负责人需同步新增 Alembic head。真实工作空间升级前如遇空历史时间戳，应由数据负责人依据记录恢复后再迁移；本次没有对现有开发/生产数据库执行升级。HTTP 接口和业务模型本身未变化。
