# Agent 2 本轮验证记录

日期：2026-10-27。工作区 `corpusflow-datasets`，分支 `feat/tc-catalog-datasets`，起始提交 `263821e6b6014ec99ff3bd816a982f44717f4c55`；开工前工作区干净。

实现范围：标准库生成器、training_center 模块离线生成模型、响应建议/场景 JSON、所属单元测试。未修改共享契约/DTO、主入口、全局错误处理、依赖清单/锁文件、数据库模型/迁移、Worker 或前端页面。

## 实际执行

环境：Windows PowerShell，Python 3.12.10。`uv sync --frozen --group dev` 成功，创建本 worktree 独立 `.venv`，使用现有锁文件，无新增依赖要求。

```powershell
python scripts/generate_training_center.py --workspace-id tc-agent2 --seed 42 --output-dir .local/training-center/agent2-default
python scripts/generate_training_center.py --workspace-id tc-agent2 --seed 42 --cpt-count 23 --sft-count 11 --dpo-count 7 --output-dir .local/training-center/agent2-small
python scripts/generate_training_center.py --workspace-id tc-agent2 --seed 42 --cpt-count 0 --sft-count 0 --dpo-count 0 --output-dir .local/training-center/agent2-empty
```

以上三个命令均 exit 0。对应目录已存在，不能原地重跑；复现时换用新输出目录。

| 配置 | CPT train/validation/test | SFT train/validation/test | DPO train/validation/test | 文件/片段 |
|---|---|---|---|---|
| 默认 2000/1500/800 | 1800/100/100 | 1350/75/75 | 720/40/40 | 860/0 |
| 小规模 23/11/7 | 21/1/1 | 10/1/0 | 6/1/0 | 13/0 |
| 空 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0 |

内容 revision：

- 默认：`5998785ea34de67d60577b5838989b9b4e4382e29e1cecb23e1b1fb8ddcbcb79`
- 小规模：`d092affb85dc269e97a6088f17195483cdf6baa03bb0e61a5a2b29409cb6567a`
- 空：`d4ecfb3f8baaef7d439f47d4c7c95ffa76255d0870224c29593f45d238ca2437`

`contract_examples.build` 已实际读取小规模与空目录导出 normal/empty/errors 三个场景包。提交的 JSON 只有分页样例与统计，无批量生成数据。`git check-ignore .local/training-center/agent2-default/manifest.json` 确认生成目录被忽略。

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/training_center --basetemp .local/training-center/pytest-final -q
.venv/Scripts/python.exe -m ruff check scripts/generate_training_center.py apps/api/src/corpusflow/modules/training_center tests/unit/training_center
.venv/Scripts/python.exe -m ruff format --check scripts/generate_training_center.py apps/api/src/corpusflow/modules/training_center tests/unit/training_center
.venv/Scripts/python.exe -m mypy apps/api/src/corpusflow/modules/training_center
```

结果：**51 passed in 8.32s**，无跳过；ruff 全部通过；6 个 Python 文件格式检查通过；mypy 严格检查 3 个模块源文件通过。

覆盖范围：局部 RNG 不影响进程状态、相同 seed/config 的内容/ID/revision/哈希稳定、时间及路径不影响内容、不同配置/工作空间隔离；默认精确数量、小数量与 0 数量；来源组在所有 kind 的 split 之间不相交且确有多记录组；source/dataset_version 引用可解析、实际 TXT 文件存在；CPT/SFT/DPO 结构及字符口径；manifest 文件清单/哈希/字节数/行数；非法 ID/数量/seed/CLI 参数；已有文件/空目录/有内容目录拒绝覆盖；完整/损坏/缺失目录行为；场景 JSON 从文件重放一致；分页稳定与边界、统计和分布总数一致、错误包裹符合现有 ErrorResponse。

## 未运行与已知边界

- 真实 HTTP、OpenAPI/共享 DTO 校验：**未运行**。本轮没有注册路由，共享 DTO 待 Agent 1 确认，不能把离线样例测试称为 HTTP 契约验收。
- 数据库/权限隔离集成、Worker、解析/清洗、导出链、旧构建审核发布流程回归：**未运行**。本轮仅静态核对既有机制，未触碰服务或共享数据。
- React/TypeScript/lint/build/Playwright：**未运行**。本轮没有前端修改。
- 仓库全量 pytest/mypy/ruff：**未运行**，执行范围为上述新增模块及所属测试。
- 人工或其他 agent 独立复核：待安排。作者自己的测试不替代独立复核。
- TXT 是本轮唯一实际来源文件格式；其他格式桶为 0。没有已执行片段、算子链、接入趋势、质量评估或准确 Tokens。
- generated 的 active revision 切换、workspace 快照缓存/保留、生产数据量上限和导出接入尚未实现。具体依赖请求见 README 的 Agent 1 清单。
