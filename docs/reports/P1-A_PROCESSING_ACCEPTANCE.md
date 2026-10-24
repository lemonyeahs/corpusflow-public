# CorpusFlow P1-A 专业文档解析与数据处理验收

日期：2026-10-24
Git 基线：`b1c54f1 feat: harden P0 system acceptance`
范围：P1-A；本轮完成后停止，不进入 P1-B/P1-C/P1-D。

## 结论

**CONDITIONAL PASS（开发/演示环境）**。

本轮已实现并在隔离 Docker 环境中验证 PDF/HTML 解析元数据增强、版本化清洗/去重/质量算子链、对象存储中间产物、NodeRun 指标、派生 DocumentVersion、处理 API 和 Web 处理页。P0 业务闭环回归通过。

正式 OCR/VLM、版面级多栏重排、复杂表格恢复、WeKnora/docreader 和 Data-Juicer 均未接入，相关测试标记 **NOT RUN**，因此不能宣称生产级专业文档解析能力。

## 实际实现

| 能力 | 实现状态 | 证据 |
|---|---|---|
| PDF/HTML 解析 | PASS | `PDFParserAdapter` 记录页/行定位、章节、公式 marker、表格行；HTML 记录 heading 和行定位 |
| 清洗算子 | PASS | `builtin.clean`，记录版本、配置快照、输入/输出/过滤数量 |
| 精确去重 | PASS | `builtin.deduplicate`，保留首条并记录过滤数 |
| 质量评估 | PASS | `builtin.quality`，输出短文本、空文本等质量统计；问题创建需显式 `create_issues=true` |
| 版本化流水线 | PASS | parse → clean → deduplicate → quality；每次 Run 固化配置哈希 |
| 中间产物 | PASS | `artifacts/{run_id}/{node_id}/output.json` 写入 MinIO，Artifact 记录 SHA-256 |
| 版本与血缘 | PASS | 内容实际变化时创建派生 DocumentVersion/Segment，并写入 LineageEdge；历史版本保留 |
| 处理 API/Web | PASS | 算子注册、NodeRun 指标、Artifact/日志、JSON 配置、轮询和失败诊断页面 |
| 外部组件 | NOT RUN | `DocReaderAdapter`、`DataJuicerAdapter` 未配置时返回 `ADAPTER_NOT_CONFIGURED` |

主要文件：

- `apps/api/src/corpusflow/adapters/processing/`
- `apps/api/src/corpusflow/services/processing_pipeline.py`
- `apps/api/src/corpusflow/worker/tasks.py`
- `apps/api/src/corpusflow/api/v1/business.py`
- `apps/web/src/pages/ProcessingPage.tsx`
- `apps/web/src/api/client.ts`、`apps/web/src/types.ts`
- `apps/api/alembic/versions/0008_p1a_processing.py`
- `tests/unit/test_processing_adapters.py`、`apps/web/tests/p1-a.spec.ts`

## 数据库与 API 变化

迁移 `0008_p1a_processing` 已执行，当前数据库版本为 `0008_p1a_processing`。变更包括：

- 新增 `operator_definitions`；
- `node_runs` 增加算子键/版本、配置快照、输入输出/过滤数量、耗时和失败码；
- `document_versions` 增加 parser、配置哈希、Run、Artifact 和状态字段；
- `segments` 增加来源定位、token 数和章节字段。

新增或扩展接口：

- `GET /api/v1/processing/operators`
- `GET /api/v1/pipeline-runs/{run_id}` 返回节点指标、配置和失败信息
- `GET /api/v1/pipeline-runs/{run_id}/artifacts`
- 资产详情返回 DocumentVersion/Segment 的 parser、定位、token 和版本信息

OpenAPI 已重新生成并通过契约测试。未引入同步执行耗时任务；Worker 只接收业务 ID，PostgreSQL 保持状态真值。

## 评测数据集与实际结果

新增 `tests/fixtures/p1a`，共 9 份可追溯的本地合成/合法测试 fixture，并在 `README.md` 和 `manifest.json` 中记录预期：普通文本 PDF、公式 PDF、表格 PDF、多栏 PDF、扫描 PDF、加密 PDF、损坏 PDF、技术 HTML、密码分析 HTML。

`scripts/benchmark_p1a_parsers.py` 的实际结果：

- 9 个样本；预期成功 6 个，实际成功 6 个；预期结果匹配率 **100%**；
- 平均耗时 **0.61 ms/文件**（本地 Python 进程，不代表生产吞吐）；
- 成功样本文本 marker 完整率和定位覆盖率均为 100%；
- 公式样本识别 2 个公式 marker，表格样本识别 3 行表格 marker；
- 扫描、加密、损坏 PDF 分别返回 `SCANNED_PDF_UNSUPPORTED`、`ENCRYPTED_PDF`、`CORRUPT_PDF`，没有生成成功 DocumentVersion。

完整样本表见 [`P1-A_PARSER_BENCHMARK.md`](./P1-A_PARSER_BENCHMARK.md)。多栏排序、OCR、复杂表格结构和真实公式语义仍是限制，当前结果没有把 marker 计数解释成完整版面恢复。

## 真实执行证据

在本地 Docker Compose 隔离环境中，PostgreSQL、Redis、MinIO、API、Worker、Dispatcher 均运行；`/ready` 返回 `200`，Compose 中 API/依赖为 healthy，迁移 head 为 `0008_p1a_processing`。

- P1-A Playwright：上传真实 PDF，创建真实处理 Run，等待 parse/clean/deduplicate/quality 节点完成，读取 Artifact 和 DocumentVersion/Segment 定位：**1 passed**；
- 全部 Web E2E（响应式、P0-H、P0-I、P1-A）：**4 passed**；
- P0-C～P0-F 业务脚本：**PASS**，包含 N=3 独立 Run、审核门控、显式恢复、不可变发布、workspace 隔离血缘；
- 解析失败路径由损坏、加密、扫描 fixture 实际触发并保留明确错误码；
- 重复执行不覆盖已有 Artifact/DocumentVersion，派生版本只在内容真实变化时创建。

## 测试结果

| 检查 | 结果 | 实际输出 |
|---|---|---|
| pytest（unit/integration/contract/e2e API） | PASS | `29 passed, 16 warnings in 7.07s` |
| Alembic migration smoke | PASS | `1 passed in 1.18s` |
| ruff | PASS | `All checks passed!` |
| mypy | PASS | `Success: no issues found in 32 source files` |
| 前端 typecheck/lint/build | PASS | 三项命令均退出 0，Vite 产物 266.91 kB |
| OpenAPI contract | PASS | 已包含在测试套件，新增算子和 Artifact DTO 校验通过 |
| Playwright 真实 Docker E2E | PASS | `4 passed (6.5s)` |
| 解析 benchmark | PASS | 9 samples，100% 预期结果匹配 |
| WeKnora/docreader 实际执行 | NOT RUN | 无 gRPC endpoint、proto client、OCR/VLM 服务和资源配置 |
| Data-Juicer 实际执行 | NOT RUN | 未锁定依赖/版本/资源和许可证闭包 |

上述 NOT RUN 项没有改写为成功，也没有用 MockAdapter 结果替代真实组件证据。

## 已知缺陷与风险

- 内置 PDF 解析依赖文本层；扫描版 PDF 目前明确失败，未提供 OCR；
- 复杂表格只保留可识别的行 marker，未承诺单元格合并和跨页结构；
- 多栏 PDF 当前保存页/行定位，但没有版面模型重排；
- 质量节点默认只输出评测统计，只有显式配置 `create_issues=true` 才写入质量问题，避免无条件阻断既有 P0 恢复流程；
- 外部解析/清洗组件接入前仍需锁定 commit/tag、许可证、输入输出契约、资源预算和回归集；
- 当前验收针对开发 Docker 环境，不等同于生产吞吐、可用性或正式身份认证验收。

## 本地复现

```bash
make init-env
docker compose --env-file .env -f infra/compose.yaml up -d
docker compose --env-file .env -f infra/compose.yaml run --rm init
uv run --locked pytest -q
uv run --locked ruff check apps/api/src tests scripts
uv run --locked mypy apps/api/src
cd apps/web && npm run typecheck && npm run lint && npm run build && npm run e2e
```

## 下一阶段依赖

进入后续阶段前，需要先完成正式身份/OIDC 方案、外部解析组件许可证和资源评估、OCR/VLM 隔离服务、复杂版面回归集，以及对 Data-Juicer 的版本锁定和结果对比。P1-A 到此停止，本轮不实施 P1-B/P1-C/P1-D。
