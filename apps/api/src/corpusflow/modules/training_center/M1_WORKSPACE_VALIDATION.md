# M1 workspace、导出与 React 页面交付

日期：2026-10-27。Agent 2（B＋G），worktree `F:/PJ/xz/corpusflow-datasets`，分支 `feat/tc-catalog-datasets`。

这三项在本轮实现，不推迟到 M2；生产路由注册、真实服务联调和独立验收仍未完成，不能称整个 M1 已验收。

## 提交与基线

- `7e2f227`：首批 generated 目录/API。
- `78a706e`：workspace 数据库快照、导出调用方控制、CPT/SFT/DPO 页面和旧构建入口适配。
- `2384753`：将已合入 Agent 3/4 的远程 main `c62b570` 合入本分支，无冲突；未操作其他 worktree 或 main。
- 后续交接提交直接接入远程已交付的 `services.processing_exports.serialize_records`，补齐真实四格式导出验证和本文。`git log` 可查该提交号。

初始工作区干净；本轮代码先提交再合入新公共基线，已有修改得到保留。没有主动编辑共享入口/DTO/锁文件/Worker/迁移。公共文件变化来自上述已授权远程基线合并，不是 Agent 2 接管开发。尚未推送本分支。

## 修改范围与行为

| 文件 | 内容 |
|---|---|
| `modules/training_center/workspace.py` | 现有数据库表适配；已发布版本；真实片段证据；900秒/10份进程快照 |
| `modules/training_center/catalog.py` | 快照增加片段、版本manifest元信息、文件关联、真实运行引用 |
| `modules/training_center/query.py` | 兼容两类目录；真实片段分布；按文件证据过滤workspace训练记录 |
| `modules/training_center/downloads.py` | 原manifest对象及SHA256验证；live授权；真实公共序列化器；完整限额检查后下载 |
| `api/v1/training_center.py` | workspace路由读取；manifest适配；新增dataset export；导出审计 |
| `apps/web/src/features/training-datasets/index.tsx`、`datasets.module.css` | 三类数据集浏览、筛选、分页、来源、分布、manifest、下载、旧构建入口 |
| `apps/web/src/pages/DatasetPage.tsx` | 可选initialProductType；CPT映射pretrain；选择同类真实workspace数据集 |
| `tests/unit/training_center/test_workspace.py` | 数据库快照/授权/manifest/真实序列化器测试 |
| `tests/contract/test_training_center.py` | 真实路由的workspace、完整split导出、审计与错误响应测试 |
| 页面目录的 `playwright.config.ts`、`__tests__/datasets.spec.ts` | 独占5192端口的浏览器交互和移动端验证 |
| 模块/页面README、历史报告提示、本文 | 集成步骤、限制及实际检查记录 |

只读DTO没有字段变更。`catalog=workspace` 现在读取数据库，不再返回未实现503。新增 `GET /api/v1/training-center/datasets/{dataset_id}/export`，必填version，可选catalog/revision/split/export_format。CPT数据库类型仍为pretrain；SFT保持messages顺序；DPO一对一个记录；未知Tokens保持null。

## 实际验证

后端使用本worktree `.venv`、隔离SQLite和真实认证/路由；配置中的PostgreSQL、Redis、对象存储指向不可连接的测试地址，未操作共享服务。对象manifest测试使用受控对象响应验证字节限制、校验和和资源关闭；不声称访问过真实S3。

| 检查 | 实际结果 |
|---|---|
| `pytest tests/unit/training_center tests/contract tests/unit/test_training_processing.py tests/unit/test_lineage_graph_api.py -q` | **240 passed in 134.27s**，合入最新远程基线后执行；包括生成器默认规模/小规模、读取器、契约、Agent 3/4相关回归 |
| `pytest tests/unit/training_center/test_workspace.py -q` | 最后修正nullable metadata证据兼容后，**21 passed in 1.23s**；含新增兼容用例，未将这次与240项重复相加 |
| Agent 2范围 `ruff check`、`ruff format --check`、`mypy` | 通过；格式14个Python文件，类型8个源文件 |
| 全仓 `ruff check .` | 通过 |
| 全仓 `ruff format --check .` | **未通过**，远程基线4个文件需格式化，见下文 |
| 全仓 `mypy` | **未通过**，远程基线5个文件15项错误，见下文 |
| `scripts/export_training_center_contract.py --check` | PASS |
| `scripts/build_training_center_examples.py --check` | PASS |
| `npm run typecheck`、`npm run lint`、`npm run build` | 合并后全部通过 |
| `npx playwright test --config src/features/training-datasets/playwright.config.ts` | 合并后 **6 passed in 15.9s**；真实Chrome、页面真实代码、HTTP层使用明确浏览器测试fixture |
| `git diff --check` | 通过 |

真实导出验证覆盖 CPT/SFT/DPO × JSONL/Markdown/CSV/TXT 12种组合：通过HTTP访问真实序列化器，检查Content-Disposition/长度、完整split行数；单元验证中文、换行、逗号、引号、SFT角色顺序及DPO完整成对内容。故障注入只用于验证中途异常、超限和失败不返回成功响应头，不作为正常导出的实现替代。

workspace测试验证：仅版本关联样本计数；草稿排除；同来源不同文件不串统计；当前片段不累加历史解析；来源引用不跨空间；快照冻结、固定过期、不续期、容量淘汰、重启失效；撤销授权后旧快照不能下载；真实manifest校验；空数据、限额、metadata证据兼容。

浏览器检查：版本选择及刷新恢复、分页后改变split重置offset、搜索空结果、SFT消息次序、DPO双列/手机单列、错误下载、409快照过期、viewer隐藏构建、CPT构建切换workspace及pretrain。首轮发现两次URL更新互相覆盖，已改成一次原子更新并回归通过。

已实际查看截图：`.local/training-center/cpt-overview.png`、`sft-samples.png`、`dpo-mobile.png`。页面布局正常；SFT截图中的下载失败是测试故意返回503的状态，不能视为当前真实序列化器仍缺失。手机宽390px未出现横向溢出。截图和测试输出均被Git忽略。

保留上游Starlette/httpx、SQLAlchemy utcnow弃用提示，以及Ant Design 5对当前React版本的兼容提示；没有改锁文件消除提示。

## Agent 1/3/4 集成请求与已知问题

1. **Agent 1**：在create_app注册 `corpusflow.api.v1.training_center.router` 并更新实际OpenAPI；当前仅测试应用挂载它，页面可自动加载但正常部署的训练中心请求尚需此注册。继续安排真实PostgreSQL、对象存储、已发布workspace与生成目录的浏览器联调。
2. **Agent 1**：确认workspace片段统计采用每份Document最新DocumentVersion；历史版本的证据仍可解析。当前900秒快照在进程内，多进程部署需共享快照或固定路由。大数据时单字段读取、缓存复制及多版本重复统计需结合实际负载评估。
3. **Agent 1**：远程基线 `api/dependencies.py:db` 缺返回类型；business将旧认证函数迁出后未显式re-export，导致rag/collection/blind_review共8项导入类型错误。建议公共db标注Iterator[Session]，旧调用方改为从dependencies导入，或显式兼容re-export。Agent 2未修改这些共享文件。
4. **Agent 4**：`api/v1/lineage_graph.py` 有6项mypy错误（DTO Literal、动态模型workspace_id）；文件还需ruff格式化。generated图接入应复用已授权目录读取器，避免页面链接仅返回未实现错误。
5. **Agent 3**：`api/v1/processing_insights.py`、`services/processing_insights.py`、`tests/unit/test_training_processing.py`需ruff格式化。公共序列化器已正常复用，不再是Agent 2导出阻塞项。TXT当前按公共实现保留完整JSON结构，若要更友好的角色标签排版由公共序列化器统一调整。
6. 对照接口仍缺稳定前后记录映射，当前404 COMPARISON_NOT_AVAILABLE，不按索引拼接。

## 未运行

- 生产create_app注册和实际OpenAPI更新：**未执行**，属于Agent 1文件边界。
- 真实PostgreSQL/S3网络联调、完整构建→审核→校验→发布→导出端到端：**未运行**。
- Worker、共享数据库迁移、共享服务重启：**未运行**。
- 全仓所有测试执行、人工/其他Agent独立复核：**未运行**；仅上表列出的定向回归。

复现命令与接口参数见同目录README；生成器默认2000/1500/800和小规模验证仍由本次240项中的原生成器测试覆盖。原始实际默认目录命令及revision保留在首批M1_VALIDATION.md，本轮未重新覆盖已有生成目录。
