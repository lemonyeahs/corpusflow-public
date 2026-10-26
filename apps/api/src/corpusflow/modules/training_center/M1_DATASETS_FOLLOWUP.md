# Agent 2：acb7ce0 基线后的数据集交付

日期：2026-10-27。分支 `feat/tc-catalog-datasets`，worktree `F:/PJ/xz/corpusflow-datasets`。

本轮完成目录适配、三类数据集页面及导出的独立工作。Agent 1 统一快照尚在开发，跨模块快照及真实服务联调仍待完成，整个 M1 尚不能称为全部验收通过。

## 基线与范围

开工检查确认正确目录/分支、工作区干净、无进行中的 merge/rebase；执行 fetch，确认目标提交存在且尚未包含后，正常合并 `acb7ce0fa31befaa203bf1213ad3eebbc4afaa06`，合并提交 `1c93698`。只解决本模块 router、README 和历史报告冲突，保留上游鉴权声明、路由注册、安全及性能修复，以及本分支 workspace/导出能力。没有 reset、clean、强推、删除工作树、合并其他开发分支或操作 main。

当前代码在之前 `78a706e`/`0506eb4` 的页面、适配器和共享序列化器接入上继续完善；没有复制重写 generated 查询/发布/退役，也没有自行修改共享 DTO、应用入口、配置、依赖锁文件、模型、迁移、Worker 或 workflow。

| 修改文件 | 本轮变化 |
|---|---|
| `api/v1/training_center.py` | 可替换 workspace provider；版本限定的样本详情；导出 q、未知分页参数拒绝、UTF-8与二进制OpenAPI描述 |
| `modules/training_center/query.py` | 样本列表/导出共用完整过滤函数；精确样本查询 |
| `modules/training_center/workspace.py` | provider接入点；按历史片段生产运行记录关联；一次分组版本样本 |
| `modules/training_center/catalog.py` | 快照增加样本→真实生产运行映射；原读取安全和性能修复保留 |
| `modules/training_center/relations.py` | 来源、文件、版本、样本及处理记录的稳定读取接口 |
| `features/training-datasets/index.tsx` | 三类样本详情抽屉/深链接；完整筛选导出；下载取消；明确版本指标；旧DPO发布后刷新 |
| `pages/DpoPage.tsx` | 可选 onPublished 回调；原构建、审核、校验和发布请求不变 |
| `tests/contract/test_training_center.py` | 实际路由、真实授权检查、隔离SQLite、完整过滤导出/详情、快照过期/隔离/撤权、provider替换、非法参数 |
| `tests/unit/training_center/test_catalog_queries.py`、`test_workspace.py` | generated完整关联、workspace历史生产运行与文件最新运行的区别 |
| `features/training-datasets/__tests__/datasets.spec.ts` | 详情深链接、manifest/空版本、导出参数、旧DPO请求；稳定等待下载错误响应 |
| 模块/页面README、历史报告提示、本文、`HANDOFF.md`、`contract_examples/openapi_followup_delta.json` | 当前能力、验证边界、可审阅的共享接口接入请求 |

页面路由为 `#/datasets/cpt|sft|dpo`。CPT沿用 pretrain；SFT保持messages顺序；DPO每对一个顶层记录；未知Tokens为null。generated实体不会自动传入旧构建请求。DatasetPage兼容适配沿用前轮实现，本轮未修改该文件。

HTTP目录前缀 `/api/v1/training-center`。新增 `/datasets/{dataset_id}/samples/{sample_id}`，复用SamplesResponse单项响应；导出 `/datasets/{dataset_id}/export` 支持q+split，导出全部匹配页且拒绝offset/limit。已有overview、stats、files、datasets及manifest均复用同一授权目录查询。完整参数和映射见 [HANDOFF.md](HANDOFF.md)。

## 实际验证

所有测试资源限于本工作树 `.local/training-center/`、临时SQLite和Playwright独占5192端口。没有访问共享数据库或执行迁移。

| 检查 | 结果 |
|---|---|
| `pytest tests/unit/training_center tests/contract/test_training_center.py -q --tb=short --basetemp .local/training-center/pytest-followup-final` | **169 passed**；含默认生成规模、小规模/空数据、manifest、安全、真实序列化器和HTTP权限测试 |
| 本轮初次扩大到 `tests/unit/training_center tests/contract` | 236 passed、1 failed：共享OpenAPI快照尚未同步；发生在新增5个非法导出参数用例之前 |
| 补齐5项后再次合跑 | Windows解释器出现access violation，位于FastAPI构造路由签名期间，中途结束；该次不得计作通过。随后将契约测试单独运行，结果补充于下 |
| `pytest tests/contract -q --tb=short --basetemp .local/training-center/pytest-contract-isolated` | **104 passed、1 failed**；完整运行结束，唯一失败仍为 `test_schema_snapshot` 的两条新增路由差异 |
| `npx playwright test --config src/features/training-datasets/playwright.config.ts` | **10 passed**；最初一轮9通过、1个下载菜单时序失败，改为键盘激活并等待真实拦截响应后全量通过 |
| `npm run typecheck` / `npm run lint` / `npm run build`（apps/web） | **全部通过**；保留既有588.93 kB统计图chunk体积警告，未开展无关重构 |
| Ruff check及format --check（所属模块、router及测试） | **通过**，15个文件格式符合 |
| Mypy（所属模块及router） | **通过**，9个source files |
| CPT详情与DPO移动端截图查看 | 已查看；详情内容、来源、双回答及分页正常；移动端无横向溢出 |

生成器默认规模测试验证 CPT 2000（1800/100/100）、SFT 1500（1350/75/75）、DPO 800（720/40/40），相同seed/config一致、来源组不跨split、所有引用可解析、manifest哈希/行数匹配、不覆盖已有目录。小规模0/1/2/7/10/11/19/23及非法数量均通过。生成器本轮未修改。

复现后端检查前使用测试环境变量：APP_ENV=test、DATABASE_URL指向`127.0.0.1:1/test`、REDIS_URL指向`127.0.0.1:1/0`、OBJECT_STORE_ENDPOINT=`http://127.0.0.1:1`，对象存储桶/密钥为测试值。HTTP测试用dependency override将数据库替换为独立内存SQLite，未连接这些外部服务。命令使用仓库 `.venv/Scripts/python.exe -m pytest`。

生成命令仍为：

```powershell
python scripts/generate_training_center.py --workspace-id <authorized-workspace-id> --seed 142
python scripts/generate_training_center.py --workspace-id <authorized-workspace-id> --seed 142 --cpt-count 23 --sft-count 11 --dpo-count 7
```

默认落入忽略的 `.local/training-center/`；已有输出拒绝覆盖，发布使用模块README所述显式publish命令。

## 未运行与已知限制

- **未运行**本轮改动的隔离PostgreSQL/S3/Worker端到端；真实对象manifest访问使用受控单测，数据库快照主要由SQLite验证。
- **未运行**旧构建→审核→发布全流程真实服务验收；浏览器验证原请求和成功反馈，不能代替实际构建物化/授权审核。
- **未运行**浏览器连接真实后端、跨模块统一快照、多进程及独立Agent 4/人工复核。
- **未运行**全仓后端单元/集成测试及全仓后端静态检查；只运行表中明确列出的范围。
- 当前workspace缓存与GraphSnapshots各自独立；共享provider尚未交付。文件对照缺持久化记录映射，保持404。
- OpenAPI共享快照测试尚未通过。差异已从真实应用生成，仅两条新路径、无新增响应schema，提交在本模块供Agent 1整合，没有改共享快照来掩盖结果。
- 运行日志包含既有Starlette TestClient和datetime.utcnow弃用警告；未修改依赖或公共模型以处理这些警告。解释器access violation需在独立环境复核，本轮不擅自归因或修复CI。

## 协作请求

Agent 1：交付统一快照provider及注入方式；补ExportQuery.q和共享OpenAPI；确认最新DocumentVersion片段统计口径。用户已明确这些接口尚在开发，本轮保留替换点并继续完成其他工作。

Agent 3：序列化器已接入；提供隔离环境真实已发布版本、training授权和可读manifest用于端到端验证；后续处理对照需要稳定记录ID映射。本轮无新依赖/模型/迁移请求。

Agent 4：使用CatalogRelations及已授权快照读取generated关联，区分source_association和真实执行证据；在共享快照落地后联合验证文件→版本→历史处理记录→图。详细接口和示例见 [HANDOFF.md](HANDOFF.md)。
