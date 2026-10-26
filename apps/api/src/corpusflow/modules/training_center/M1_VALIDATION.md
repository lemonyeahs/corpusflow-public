# M1 首批验证与交接

> 本文保留 `7e2f227` 首批的历史结果。workspace、导出及 React 页面已在后续实现，最新状态见 [M1_WORKSPACE_VALIDATION.md](M1_WORKSPACE_VALIDATION.md)。

日期：2026-10-27。Agent 2（B＋G），独立 worktree `corpusflow-datasets`，分支 `feat/tc-catalog-datasets`。共同基线 `58fe070955b3a8c66806dc8f2d8ed2f152d5036d`，开工前工作区干净。契约版本 `1.0.0`。

## 交付范围

- 新增 `modules/training_center/catalog.py`、`query.py`、模块 README 与本报告。
- 新增 `api/v1/training_center.py`，9 个只读 GET 路由；生产入口尚待 Agent 1 注册。
- 新增目录读取/查询测试两份，HTTP 契约测试 `tests/contract/test_training_center.py`。
- 未改共享 DTO、main.py、business.py、配置、锁文件、Worker、数据库模型/迁移或 React 页面。无新依赖。

实现的是 generated 首批后端，不代表整个 M1 完成。workspace 数据库适配/快照、导出、数据集页面与旧构建页适配留待后续批次。跨模块接入请求与明确代码位置见 [README](README.md)。

## 实际检查

环境为本 worktree `.venv`、Python 3.12.10、Windows PowerShell。测试进程使用 test 配置，PostgreSQL/Redis/对象存储配置均指向 `127.0.0.1:1` 和测试用字符串；不加载生产凭据、不连接共享服务。HTTP 测试只 override db，使用每个测试独立的内存 SQLite 与实际 User/Workspace/Membership 表，保留真正的 actor_id/workspace_id 授权函数。FastAPI 使用现有 create_app 与错误处理中间件，在测试中挂载新 router。

| 命令/检查 | 实际结果 |
|---|---|
| `python -m pytest tests/unit/training_center tests/contract -q --basetemp .local/training-center/m1-regression` | **198 passed in 80.15s**，无 skip；包含新增74项及原生成器/共享契约/OpenAPI检查 |
| `python -m ruff check .` | 全仓通过 |
| `python -m ruff format --check .` | 163 个 Python 文件通过 |
| `python -m mypy` | 64 个源文件通过 |
| `python scripts/export_training_center_contract.py --check` | PASS，无 TypeScript/设计 OpenAPI 漂移 |
| `python scripts/build_training_center_examples.py --check` | PASS，无统一样例漂移 |
| `python -m pytest --collect-only -q -m 'not integration'` | 成功收集330项，15项integration deselected，无同名测试导入冲突；仅收集，不声称执行了330项 |
| `git diff --check` / 暂存差异检查 | 通过 |

首轮检查发现一项 zip 未显式指定 strict 的 lint 问题，已修正后执行上表检查。保留已有 Starlette/httpx 与 SQLAlchemy utcnow 弃用提示，不新增依赖或改动共享模型来消除历史警告。

覆盖：发布前不可读、活动指针切换、固定旧版本、显式退役与当前/前一版本保护、发布失败原子保留旧指针；完整 manifest hash 固定时间元数据；文件字节/哈希/行数/引用/计数/字符数/来源组隔离；大小和mtime不变的篡改仍被检出；路径穿越、symlink/junction、workspace 错配、重复 JSON key、缺失文件、损坏目录；有界缓存与返回副本；100000条/100MiB限制及恰好到界；排序、过滤后分页、所有分布/流转使用同范围与正确单位；空数据、缺失时间与时区日期补零；路由请求参数解码、现有错误包裹、真实成员权限查询、越权403/隐藏对象404、禁用用户401、暖缓存后撤销成员仍403、workspace 未实现503、无清洗对比404、超限413。

## 实际默认规模命令验证

```powershell
python scripts/generate_training_center.py --workspace-id tc-m1-local --seed 142
.venv/Scripts/python.exe -m corpusflow.modules.training_center.catalog publish --workspace-id tc-m1-local --revision fa9f419def622dffd839098dc43ac1c97b025ddf3d9eaf8ddc9b23fb23b5e8d0
```

均退出0，之后实际调用 GeneratedCatalog.load 与 CatalogQueries.overview/stats 成功：CPT2000、SFT1500、DPO800，顶层记录4300，文件860，片段0，Tokens和质量均null；来源文件分布 web308/book278/paper274。所有生成目录、索引与测试临时文件仅位于忽略的 `.local/training-center/`。该本地目录名并未自动注册为数据库工作空间，实际HTTP部署须使用真实获授权的workspace ID。

## 未运行与依赖

- 新 router 在生产 create_app 中注册、实际 OpenAPI 更新：**尚未执行**，交 Agent 1。
- 真实 PostgreSQL HTTP/独立进程网络端到端、Worker、数据库迁移及共享服务操作：**未运行**。SQLite/TestClient 验证不能替代这些检查。
- React/浏览器、旧构建审核发布及数据集导出：**未运行**，本批没有修改这些功能。
- 全仓非集成330项执行：**未运行**；本批执行198项相关回归，并完成全仓收集及静态检查。
- 人工/其他 agent 独立复核：待安排。本批由作者验证，不能作为独立验收结论。

Agent 1 可直接注册当前 router 后进行真实目录联调；Agent 4 可复用已授权的 GeneratedCatalog.load 获得同一 revision 的来源、文件、数据集和样本。Agent 3 后续提供处理产物的持久化结构及通用序列化器后，再扩展 processed generated/workspace 与导出；当前明确拒绝未支持的结构，不返回样例或伪造成功。
