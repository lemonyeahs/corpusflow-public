# 两人、四个 agent 协作指南

状态：当前团队执行配置。本文补充原并行任务书，把 A～H 八类职责分配给四个 agent；本次提交包含计划、契约草案与视觉原型，不代表功能开发已经完成。

## 1. 同伴与 agent 从哪里开始

所有参与者先同步同一个仓库基线，再阅读：

1. 仓库根目录 [AGENTS.md](../../AGENTS.md)。
2. 本指南。
3. [并行开发任务书](TRAINING_CENTER_PARALLEL_PLAN.md)。
4. [共享接口契约](../specs/TRAINING_CENTER_CONTRACT_V1.md)。
5. [HTML 原型](../previews/training-data-center.html)；原型可直接用浏览器打开，不依赖后端。

不要假设 agent 能读取别人的聊天记录。把下面的身份和任务提示明确发给它。即使工具支持自动读取 AGENTS.md，首次启动仍应明确要求读取这些文件。

文档在各自机器上使用仓库相对路径；不复制发起人的 F: 盘绝对路径。

## 2. 两个人如何管理四条开发线

| 人工负责人 | Agent | 原任务书角色 | 文件范围与职责 |
|---|---|---|---|
| 负责人甲：体验与集成 | Agent 1 | A＋E | 应用骨架、路由、公共主题/契约/组件、依赖、首页、数据台、集成 |
| 负责人甲：体验与集成 | Agent 2 | B＋G | 数据生成、manifest、统计及只读 API、三类训练数据页、现有构建页适配 |
| 负责人乙：处理与正确性 | Agent 3 | C＋F | 解析器、清洗算子、处理记录、Worker/迁移、接入页、导出 |
| 负责人乙：处理与正确性 | Agent 4 | D＋H | 多跳血缘 API、血缘图、验收脚本和跨模块回归 |

- 甲审查视觉、交互、共享基础与最终合并。
- 乙审查统计口径、解析/清洗结果、血缘证据与迁移。
- Agent 4 的血缘代码不能只由 Agent 4 自己验收；乙或 Agent 3 独立复核。
- 两人可调换甲/乙，但同一开发周期内保持责任明确。
- 四个 agent 能并行编码，人工决策、代码审查与集成仍由两个人承担，排期不能按四名独立开发者等比例估算。

## 3. 每个 agent 必须使用独立 worktree

建议分支和目录：

| Agent | 分支 | worktree 目录示例 |
|---|---|---|
| 1 | `feat/tc-shell-explorer` | `../corpusflow-shell` |
| 2 | `feat/tc-catalog-datasets` | `../corpusflow-datasets` |
| 3 | `feat/tc-processing-ingestion` | `../corpusflow-processing` |
| 4 | `feat/tc-lineage-validation` | `../corpusflow-lineage` |

同一仓库目录里开四个对话、分别切换分支不构成隔离。agent 工具的工作目录必须指向自己的 worktree。

首次创建示例（在 PowerShell 中运行；分支/目录已存在时先检查，勿强制覆盖）：

```powershell
git fetch origin
# 将下方值替换为双方确认过、且已推送的共同基线提交。
$tcBase = '<共同基线提交号>'

# 甲只需创建自己管理的两个 worktree：
git worktree add -b feat/tc-shell-explorer ../corpusflow-shell $tcBase
git worktree add -b feat/tc-catalog-datasets ../corpusflow-datasets $tcBase

# 乙在自己的仓库创建另外两个：
git worktree add -b feat/tc-processing-ingestion ../corpusflow-processing $tcBase
git worktree add -b feat/tc-lineage-validation ../corpusflow-lineage $tcBase
```

共享基线必须是双方仓库都能访问的提交。首次可以使用本套文档的提交，M0 合并后再协调同步新的公共骨架基线。

每个 worktree 安装自己的依赖；不要共享可变的 node_modules、.venv 或生成目录。`.env` 不进入 Git，各自初始化本地配置。共用后端时由指定负责人管理服务；需要隔离后端时使用独立 Compose 项目名、端口、卷和队列。

## 4. 启动指令模板

把这段发给每个 agent，填写四处占位信息：

```text
我们正在开发 CorpusFlow 训练数据中心，采用两个人、四个 agent 的协作方式。

开始前完整阅读：
- AGENTS.md
- docs/plans/TRAINING_CENTER_AGENT_COLLABORATION.md
- docs/plans/TRAINING_CENTER_PARALLEL_PLAN.md
- docs/specs/TRAINING_CENTER_CONTRACT_V1.md
视觉参考：docs/previews/training-data-center.html

你的身份：【Agent 1 / 2 / 3 / 4】
你的工作目录：【该 agent 的独立 worktree】
你的分支：【对应开发分支】
本轮任务：【一个明确、可验收的小任务】

先检查当前分支和工作区，再概括你的任务、文件范围和依赖。
按照文档的文件归属工作，不修改他人的文件或清理他人的改动。
共享契约/配置变动提交给对应负责人，不自行创建另一套字段或协议。
不自行合并其他开发分支，不操作未分配给你的共享数据库和服务。
共享基线尚未完成时，先做分析、样本和独立模块，继续推进不依赖基线的工作。
发现冲突或越界需求时说明具体问题；不要因此停止所有独立工作。

交付时报告：修改文件、提交号（如已提交）、接口变化、验证命令与结果、
已知问题，以及需要其他 agent 配合的事项。未运行的检查明确标注未运行。
```

本轮任务必须具体。例如 Agent 3 的第一轮可以是“文本解析器与边界测试”，而不是一次性要求“完成全部后端”。

## 5. 执行顺序与建议首批任务

### M0：公共基线

- Agent 1：路由壳、主题作用域、认证上下文、QueryClient、公共组件最小接口和依赖；整合契约与开发样例。
- Agent 2：核对样本/manifest/统计模型，给出首页和样本查询响应样例，准备固定种子生成器。
- Agent 3：核对 ParserAdapter/ProcessingResult、实际执行记录、导出接口，准备解析和算子边界样本。
- Agent 4：核对现有 LineageEdge 和算子记录，给出图响应样例，整理验收清单。

M0 只完成共同骨架和接口约定，不要求所有页面/业务实现。甲审查后把公共基线提交推送；乙同步给 Agent 3/4。

### M1：四线并行

- Agent 1：先首页，再格式数据台；按批次注册其他模块入口。
- Agent 2：先生成器＋只读样本接口，再数据集页面；适配 CPT 到现有 `pretrain` 产品类型。
- Agent 3：先文本/JSONL/CSV/DOCX 与 JSON 分支，再清洗与记录，接入页同步以契约开发。
- Agent 4：先图查询与交互，再连接实际处理记录；持续补充验收用例，不把全量验收提前当作唯一工作。

每个 agent 一次交付一个可检查的目标，接口逐个就绪后逐个替换开发样例。

### M2：联调

- Agent 1 ↔ Agent 2：主页统计、格式筛选、文件对比、关联数据集。
- Agent 3 ↔ Agent 4：实际算子执行、输入输出引用、多跳血缘。
- Agent 2 ↔ Agent 3：通用导出序列化器、生成文件实际处理。
- Agent 2 ↔ Agent 4：生成来源查询与数据集/样本血缘。

甲负责整理集成候选提交；乙验证处理与数据关联。Agent 4 进入回归主阶段，但不独立批准自己的实现。

### M3：审查与交付

Agent 1 集成、Agent 4 执行回归，Agent 2/3 修复所属模块问题。两名人工负责人审查结果后完成合并/发布决策。

## 6. 交接消息模板

每次发送 PR、分支或提交时，两个人使用同一格式：

```text
交付方：Agent 3 / 负责人乙
共同基线：<commit hash>
交付分支：feat/tc-processing-ingestion
交付提交：<commit hash>
本次目标：文本解析器与边界错误处理
修改范围：<目录/文件>
接口变化：无 / <字段、行为及契约版本>
验证结果：<实际执行的命令与结果>
已知问题：<问题或无>
需要对方配合：<例如 Agent 1 更新依赖并注册路由>
建议下一步：<接收人及动作>
```

接收方先检查提交内容与接口差异，再按双方约定 merge/rebase。工作区有未提交改动时先保存，不使用 `reset --hard` 强行追平，也不同时 cherry-pick 和 merge 同一组改动。

## 7. 共享规则如何更新

1. 用户的新要求由人工负责人确认后写回文档，不能只留在某个 agent 对话里。
2. 共享契约由 Agent 1 汇总修改，B/C/D 对应的 Agent 2/3/4 提供字段和行为需求。
3. 变更消息附文档/契约提交号、受影响 agent、是否兼容；双方明确下一批开发使用哪个版本。
4. 不并行维护四份互不一致的任务书；模块内可以维护自己的进度记录，但共享规则以仓库文档为准。
5. 仓库推送失败时，明确区分“本地已提交”和“远程已同步”。先解决账号写权限，或由拥有权限的人接收提交；不能把个人 fork 当成已经更新原远程。

## 8. 完成标准

最终沿用原任务书的共同完成定义：真实接口与处理链通过验收、统计同范围一致、血缘有执行依据、三类数据可浏览/导出、原构建流程保留、文档与生成 provenance 完整。静态原型和开发请求样例不等于业务交付。
