# P1-D 真实 RAG 检索、评测与反馈验收

日期：2026-10-25。起点：`fb5fd48`。结论：**CONDITIONAL PASS，仅适用于隔离开发/演示环境的词法检索验证**。真实索引、查询、评测、反馈重工及历史保护通过；向量检索、模型回答质量和领域专家核对不在通过范围。未进入 P2，未执行远程 push。

## 功能与边界

| 能力 | 状态 | 实际实现与证据 |
|---|---|---|
| 从发布 RAG 产品建立索引 | PASS | MinIO 实际 JSONL/Manifest → 哈希、候选及证据校验 → PostgreSQL Chunk；不从文件名推测关联 |
| 异步索引与评测 | PASS | Outbox → Redis → Celery `rag_job`；消息仅业务 ID；queued/running/succeeded/failed；完成前不提供查询 |
| 幂等与历史保护 | PASS | workspace/request_key 唯一约束、事务锁；真实并发请求和重复 Celery 消息；完成索引、Chunk、Trace、Suite、评测受数据库触发器保护 |
| 真实召回与重排 | PASS | PostgreSQL simple FTS、Unicode 中日韩汉字二元字符/拉丁词 BM25、词法 RRF、可选词项覆盖重排；各分数和重排前后排名独立记录 |
| 授权与空间隔离 | PASS | 当前 RAG 用途证据、成员状态、数据版本状态、片段质量、来源问题重检；撤权后新查询及历史 Trace 均屏蔽正文 |
| 引用与血缘 | PASS | Hit 保存发布 sample、Segment、DocumentVersion、Asset、Source、原文位置；复用原血缘页 |
| 低证据与模型缺席 | PASS | NO_EVIDENCE / LOW_EVIDENCE / EVIDENCE_FOUND；生成始终 NOT_CONFIGURED，answer=null，无伪造回答或引用 |
| 固定评测与对比 | PASS（合成语料） | 31 个不同问题，6 个实际实验、186 次评测查询；同一 Suite SHA；四种策略/重排组合、三个真实发布版本 |
| 反馈、复核和重工 | PASS | RagFeedback → QualityIssue → 审核 → 显式恢复原 Run → 新 DocumentVersion/Segment → 新发布版本/索引 → 同集复测 |
| Web | PASS | 版本/索引选择、异步状态、实际分数/文本/位置、Trace、评测历史、失败案例、反馈/复核/恢复、窄屏；操作调用真实 API |
| pgvector/Embedding/语义混合 | NOT RUN | 当前 PostgreSQL 16 镜像的可用扩展不含 vector；没有真实 Embedding Provider；仅保留协议边界，不生成假向量 |
| LLM、学习型 Reranker、LLM Judge | NOT RUN | 无真实服务配置；模型成本 null、回答质量 NOT_EVALUATED |
| 专业语料专家评审 | NOT RUN | CC0 原创合成说明和参考答案由代理编写；开发 reviewer 身份只验证流程，不能视为人类专家标注 |

本阶段的“混合”明确指 FTS 与 BM25 的词法融合。关键词命中不是事实支持度：含 AES 的无答案问题仍可召回 AES 片段，已保留为评测失败，不声称回答正确。

## 数据库、API 与执行协议

新增迁移 `0011_p1d_rag`，从 `0010_p1c_quality_guards` 升级：

- `rag_index_versions`：数据版本、内容哈希、配置、状态、错误、创建者、幂等键。
- `rag_chunks`：实际正文和 SHA-256、sample/segment/asset 外键、来源定位；GIN FTS 索引。
- `retrieval_traces`：独立 query、策略、原始分数、排名、命中快照、耗时。
- `rag_evaluation_suites`：发布 Evaluation 产品、冻结案例、核对说明、审核身份、SHA。
- `rag_evaluation_runs`：Suite/Index/config、状态及不可变指标/案例结果。
- `rag_feedback`：Trace、可选评测 case、Segment、现有 QualityIssue、责任模块和说明。

最新 head 为 `0012_legacy_schema_alignment`。0012 修复旧库 P1-A/C 的 JSON→JSONB、时间戳 NOT NULL 和 document_versions.run_id 索引偏差。迁移前检查历史时间戳；若缺失则抛出 LEGACY_TIMESTAMP_MISSING 并整体回滚，不编造时间。当前旧库 11 张相关表在迁移前后的逻辑行摘要完全相同，`alembic check` 返回 No new upgrade operations detected。独立迁移测试还重建了旧列类型/缺失索引、验证空时间戳安全阻断，再以测试自身已知时间修复后重升。JSON 配置/报告使用 JSONB；完整 DDL 见迁移。没有重建既有数据库或改写历史发布对象。早期 0001/0002 的动态 `create_all` 会错误预建未来迁移表，已固定其建表名单；Alembic 连接在 finally 中释放。升级、降级到 base、重升和 schema check 在独立随机数据库完成。旧迁移仍有读取当前模型定义的历史技术债，未把这次名单修复描述为完全冻结了所有旧列定义。

| 路径（均以 `/api/v1` 开头） | 方法 | 角色/行为 |
|---|---|---|
| `/rag/capabilities`、`/rag/versions` | GET | 工作空间成员；真实可用策略和已发布 RAG/Evaluation 版本 |
| `/rag/indexes` | POST / GET | 工程师/管理员提交；成员查询；POST 202 不代表成功 |
| `/rag/indexes/{id}` | GET | 作用域内状态、数量、配置、错误和哈希 |
| `/rag/queries`、`/rag/traces/{id}` | POST / GET | 当前授权重检、独立 Trace、撤权屏蔽 |
| `/rag/suites` | POST / GET | 审核员/管理员冻结已发布评测产品；成员查询元数据 |
| `/rag/evaluations`、`/rag/evaluations/{id}` | POST/GET、GET | 工程师/管理员异步提交；历史报告与失败案例 |
| `/rag/feedback` | POST / GET | 工程师/审核员/管理员创建；复核/恢复复用原 QualityIssue/Run API |

新增请求 DTO 已纳入 `docs/api/openapi.json`。典型错误：NOT_FOUND、PERMISSION_DENIED、PURPOSE_GRANT_MISSING、RAG_INDEX_NOT_READY、RAG_SCOPE_TOO_LARGE、IDEMPOTENCY_KEY_REUSED、INVALID_SAMPLE_EVIDENCE、MATERIALIZATION_HASH_MISMATCH、QUALITY_GATE_FAILED、ADAPTER_UNAVAILABLE、RAG_EXECUTION_ERROR。无权限不回退到模拟结果。

索引和评测在 Worker 中持行锁并原子提交；重复投递等待或返回已有终态；可恢复异常最多重试三次。失败保留记录，使用新幂等键重建。索引进度目前是阶段状态和最终数量，尚无逐 Chunk 百分比。新 RAG 任务的强制杀进程恢复专项 **NOT RUN**，不能用本轮重复投递测试替代故障注入。

## 实际测试

| 命令/检查 | 最终结果 | 证据 |
|---|---|---|
| `make check` | PASS | Ruff 全仓检查、83 个 Python 文件格式检查；Mypy 38 个源文件；65 passed / 4 deselected |
| `.venv/bin/python scripts/verify_p1d_environment.py` | PASS | 69 passed，0 skipped（10.20 秒）；含契约、真实 PostgreSQL 迁移及 3 项 MinIO 集成 |
| `CF_EXPECT_STORAGE_PERSISTENCE=1` 同上 | PASS | 使用先前写入的哨兵，实际 MinIO 容器重建后读回；保留原命名卷 |
| `.venv/bin/python scripts/verify_business_loop.py` | PASS | P0-C、P0-D、P0-E、P0-F PASS；默认拒绝/审核/恢复/发布/血缘回归 |
| `.venv/bin/python scripts/verify_p1d_rag.py`（由 Web E2E 调用） | PASS | 10 个真实业务检查，31 cases，6 experiments；API/PG/MinIO/Redis/Worker 全链路 |
| `npm run typecheck`、`npm run lint`、`npm run build` | PASS | TypeScript、ESLint、Vite 实际构建 |
| `npm run e2e` | PASS | 7 passed（22.8 秒）：P0-H、P0-I、P1-A、P1-B、P1-C、P1-D 和窄屏 |
| Docker Compose `up -d --build --wait api worker dispatcher` | PASS | 镜像真实重建，API/PG/Redis/MinIO 就绪；Worker/Dispatcher 通过真实消费验证 |
| 远程 CI / 生产 / 外部模型 | NOT RUN | 本轮禁止 push/生产；未配置外部模型 |

原始运行日志位于 `.local/p1d/`；小型可提交证据见 [P1-D_EVIDENCE.json](P1-D_EVIDENCE.json)。全量 pytest 有 1980 条弃用警告，主要来自既有 ORM `datetime.utcnow` 和 Starlette/httpx；没有将警告伪装成零风险，也未临时删除依赖或降低断言。

本轮经历并修复/复测：

1. Web 新下拉框的可访问名称包含选项，补充明确 aria-label；窄屏长 SHA/JSON 溢出，改为可换行、可滚动。
2. 旧上传页来源创建未返回即可上传，现按来源和 busy 状态禁用，失败有明确反馈；补真实 Web 断言。
3. 修改查询/索引/策略/Top-K/重排设置清空旧结果，防止混用检索快照。
4. 终态质量问题禁止重新审核；反馈不能打开 rejected/isolated/running/queued Run；新增四种状态回归。
5. 指标去重保留原始排名，避免重复 Chunk 抬高 Recall 或压缩 MRR 排名。
6. 现有旧库 schema check 失败，而空库检查通过；新增 0012，验证旧库数据摘要不变并重新运行旧库 check 与迁移测试。
7. 一次存储测试与 Compose 重建重叠产生 502/ADAPTER_UNAVAILABLE；保留 `pytest-during-recreate.log`、`business-during-recreate.log`，待真实服务就绪后全部重跑通过。不是业务成功，也未删除失败记录。

## Docker 前置问题复核

P1-C 的 hatchling 下载超时有历史日志依据。原构建在复制全部 API 后安装依赖，代码变动使依赖层失效，且构建后端未固定；网络延迟的外部原因无法由一次超时反推。改为依赖层前置、BuildKit uv 缓存、120 秒下载超时、固定 hatchling 1.32.4；继续保留固定基础镜像摘要和 `uv sync --locked`。本轮实际构建与重复缓存构建成功，见 `docker-build.log` 和 `docker-build-final.log`。没有清空用户镜像/数据卷，也没有关闭锁定校验；未宣称离线全新机器构建已经验证。

## 主要变更

核心代码：`adapters/retrieval.py`、`services/rag.py`、`api/v1/rag.py`、`db/models.py`、`worker/tasks.py`、`scripts/dispatch_outbox.py`。前端：`RagPage.tsx`、`api/rag.ts`、App 导航、样式、上传页防竞态。测试：`test_retrieval.py`、`test_rag_policy.py`、`p1-d.spec.ts`、真实业务/环境脚本、原创 fixture。API、计划、评测、反馈和追踪文档同步更新。若干旧 Python 文件只有 Ruff 格式/导入整理，无业务逻辑改动；完整改动清单以本地提交 `git show --stat` 为准。

## 复现与回滚

```bash
cd /Users/leon/Desktop/data
uv sync --locked
# 初次环境用 make init-env 生成本地配置；已有 .env 不覆盖。
docker compose --env-file .env -f infra/compose.yaml up -d --build --wait api worker dispatcher
make check
.venv/bin/python scripts/verify_p1d_environment.py
.venv/bin/python scripts/verify_p1d_rag.py
.venv/bin/python scripts/verify_business_loop.py
cd apps/web
npm ci
npm run typecheck && npm run lint && npm run build
npm run e2e
npm run dev -- --host 127.0.0.1
```

环境脚本只接受 loopback 数据库/MinIO，迁移测试新建并删除自身随机测试数据库；存储测试使用 `cf-verify-p1d`，不会清空用户桶。业务验证创建独立工作空间和原创测试资料，保留证据。`.local/p1d/web.json` 含开发会话，只用于本地测试，已被 `.gitignore` 排除。

回滚前停止生产者/Worker并备份开发库。0012 属于前向结构修正，降至 0011 保留规范化列/索引，不尝试恢复 JSON 原始空白或重新引入结构偏差。无 P1-D 历史数据时可在本地回退到 `0010_p1c_quality_guards`；downgrade 会删除本阶段六张表及其索引/触发器，**不适合保留已产生的 P1-D 历史**。已有历史时优先代码回退和前向修复；不得用删库/删卷处理失败。旧 DatasetVersion/Manifest/发布文件不受本迁移改写。

## 限制与 P1 整体验收建议

- 开发身份尚非 OIDC，生产启动继续默认拒绝；不具备生产身份保证。
- 当前最多 5000 Chunk/索引、100 case/Suite；BM25 在当前授权集合线性计算，未做大规模吞吐/持续负载验收。列表有 100/200 条上限，尚无全量分页导出。
- 二元字符不是完整中文分词；没有语义同义扩展。公式只检索字符/数字词项，不解释数学语义；HTML 原文位置是行号，不能伪称 PDF 页码。
- no-answer 误命中暴露了词法相关与证据充分性之间的差距。LOW_EVIDENCE 为词项覆盖启发式，不是置信概率或正确性保证；回答生成保持关闭。
- 反馈暂按来源资产保守阻断，待复核并重工解决；未提供“无需加工直接消除问题”的新状态机。索引不独立提供销毁/退役 API，消费时重检发布状态和当前授权。
- 真实向量/生成 Provider、学习型重排、领域专家标注、外部成本和回答评测仍未执行。Prompt 注入仅验证为不执行的证据文本，不能据此宣称已防御真实 LLM 注入。

建议 P1 总验收保留 CONDITIONAL PASS：先由业务专家核对评测集和来源许可，再在独立评审后接入正式身份/真实模型或向量服务，随后增加中文专业语料、对抗问题、模型引用校验、故障注入与规模测试。本轮到此停止，不自动启动后续工作。
