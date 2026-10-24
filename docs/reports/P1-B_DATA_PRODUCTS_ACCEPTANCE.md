# CorpusFlow P1-B 多类型数据产品验收

日期：2026-10-24  
Git 基线：`356f951 feat: add P1-A document processing pipeline`  
范围：预训练语料、RAG 知识片段、评测数据集；本轮完成后停止，不进入 P1-C/P1-D。

## 结论

**CONDITIONAL PASS（开发/演示环境）**。

三类产品已通过统一构建、候选审核、用途授权、质量门控、不可变物化、Manifest、下载和血缘链路。现有 SFT 继续复用同一套服务并回归通过。当前没有实现在线 RAG、向量检索、Rerank、DPO 或正式模型效果评测。

## 完成状态矩阵

| 能力 | 状态 | 实现与证据 |
|---|---|---|
| 统一 Builder 接口 | PASS | `services/dataset_builders.py` 注册 SFT/Pretrain/Rag/Evaluation Builder |
| 预训练语料 | PASS | 按来源连续组织、内容去重、长度过滤、source-group 划分、真实 token 统计 |
| RAG 片段 | PASS | token/char 单位、chunk size/overlap、来源/版本/页码定位、`all` 划分 |
| 评测数据 | PASS | question/reference/evidence Schema、重复题检测、人工审核和证据门控 |
| 用途级授权 | PASS | training/rag/evaluation 固定映射，构建时先过滤授权不通过的 Segment |
| 共享发布链路 | PASS | 复用 DatasetBuild/CandidateSample/Materializer/Manifest/MinIO/Outbox/lineage |
| 配置快照 | PASS | `DatasetBuild.config_json`、`config_hash`、验证快照哈希不可变 |
| 物化与下载 | PASS | 三类真实 JSONL、MinIO 不可变对象、Manifest SHA-256、短期签名 URL |
| Web 数据产品中心 | PASS | 产品类型、RAG 参数、评测 JSON、候选预览、审核和发布下载均接真实 API |
| 在线 RAG/向量检索 | OUT OF SCOPE | P1-D |
| DPO | OUT OF SCOPE | 用户明确排除 |

## 统一架构与代码变化

新增 `DatasetBuilder`、`BuiltCandidate`、`BuildResult`，产品 Builder 只负责产品专属 Schema 和转换；授权、审核、质量门控、发布、对象存储、审计和 lineage 保持共享。

主要文件：

- `apps/api/src/corpusflow/services/dataset_builders.py`
- `apps/api/src/corpusflow/services/dataset_materializer.py`
- `apps/api/src/corpusflow/api/v1/business.py`
- `apps/api/src/corpusflow/main.py`
- `apps/web/src/pages/DatasetPage.tsx`
- `apps/web/src/api/client.ts`、`apps/web/src/types.ts`
- `tests/unit/test_dataset_builders.py`
- `scripts/verify_p1b_products.py`
- `apps/web/tests/p1-b.spec.ts`

本轮没有新增数据库表或迁移。已有 `DatasetBuild.config_json`、`CandidateSample.payload` 和 `DatasetVersion` 字段足以保存产品配置、Schema、候选和发布统计；数据库当前仍为 `0008_p1a_processing`。后续若需要查询型评测索引，再单独设计迁移，不在本轮隐式扩表。

## API 变化

- `GET /api/v1/dataset-products/types`：返回产品类型、固定用途和 Schema 版本。
- `POST /api/v1/datasets`：支持 `sft`、`pretrain`、`rag`、`evaluation`。
- `POST /api/v1/dataset-builds/preview`：返回产品类型、授权纳入/排除和 Schema 版本。
- `POST /api/v1/dataset-builds`：根据产品类型调用 Builder，保存授权过滤、排除原因和 Builder 指标。
- `GET /api/v1/dataset-builds/{build_id}/candidates`：返回产品 payload 预览。
- `GET /api/v1/dataset-builds/{build_id}/quality-report`：返回构建指标、过滤、审核和候选统计。
- 现有 validate/publish/manifest/download/lineage API 扩展为识别产品 Schema 和 `all` 划分。

新增错误码：`PRODUCT_PURPOSE_MISMATCH`、`UNSUPPORTED_PRODUCT_TYPE`、`NO_VALID_CANDIDATES`、`INVALID_CHUNK_CONFIG`、`INVALID_CHUNK_UNIT`、`INVALID_EVALUATION_CONFIG`。

## 三类真实发布结果

以下结果由 `scripts/verify_p1b_products.py` 在本地 Docker API/PostgreSQL/Redis/MinIO 中实际执行。每个产品都完成审核、验证、发布、Manifest 读取、签名 URL 下载和 SHA-256 校验。

| 产品 | 版本 | 样本数 | 文件字节 | JSONL SHA-256 |
|---|---:|---:|---:|---|
| pretrain | 2.0.79496 | 1 | 393 | `669f8f815d6d86e31cc76491314e70a3d44f8000f7310ab7a10858465eb15157` |
| rag | 2.0.6825 | 1 | 600 | `3c0e4bb4da50c11d993c3b8a8baa5792fa6c287648ac9d81243a5dc0ddb1984d` |
| evaluation | 2.0.33421 | 1 | 538 | `7a86cab00dee41d3b041f28018697978ce66f23f4d02a1e5542a1f40ad6485be` |

完整实际 JSONL 首行、dataset/version/build、Schema、来源和配置摘要见 [`P1-B_DATASET_SAMPLES.md`](./P1-B_DATASET_SAMPLES.md)。

## 质量、授权与一致性验证

- 训练用途授权通过的数据成功生成预训练数据；用途不匹配的预训练构建返回 `PRODUCT_PURPOSE_MISMATCH`。
- RAG Builder 使用 `chunk_size=3, overlap=1`，同一输入的不同 chunk 配置会产生不同候选数量；每个 Chunk 保留 source、asset 关联的 DocumentVersion、Segment 和定位。
- 评测样本必须有 question、reference_answer、evidence_ids 和 source_ids；缺少证据或参考答案不通过产品 Schema，物化阶段再次阻断。
- 评测候选不调用模型服务；当前验收使用人工提供的 reference answer，未将 Mock/固定生成结果标记为模型生成。
- 同一版本重复发布返回同一 DatasetVersion；对象键带 dataset/version，发布后不会覆盖。
- Manifest 中 SHA-256 与通过签名 URL 读取的 MinIO 文件实际 SHA-256 一致。
- 下载用途重新校验版本候选的 LicenseGrant；跨 workspace Manifest 查询返回 404。
- CandidateSample → DatasetVersion、Segment → DatasetVersion、Source → DatasetVersion 的 lineage edge 可查询。

## 测试结果

| 检查 | 结果 | 实际输出 |
|---|---|---|
| pytest 全量 | PASS | `37 passed, 16 warnings in 7.38s` |
| Builder/materializer 单元测试 | PASS | 包含预训练分组、RAG 参数差异、评测 Schema/证据门控 |
| Alembic migration smoke | PASS | `1 passed in 1.80s`；当前 head `0008_p1a_processing` |
| ruff | PASS | `All checks passed!` |
| mypy | PASS | `Success: no issues found in 33 source files` |
| OpenAPI contract | PASS | 已重新导出 `docs/api/openapi.json`，unit/contract 全部通过 |
| 前端 typecheck/lint/build | PASS | 三项命令退出 0，Vite 产物 268.80 kB |
| P0-C～P0-F 业务回归 | PASS | `verify_business_loop.py` 四项 PASS |
| P1-B 三产品 MinIO E2E | PASS | `P1-B PRODUCTS PASS`，三类文件均下载并校验哈希 |
| Playwright 全量真实 Docker | PASS | `5 passed (6.4s)`，含 P1-B RAG 页面构建/发布/Manifest |
| P1-A 关键回归 | PASS | P1-A Playwright 和现有处理链通过 |

## 未完成事项和风险

- 当前预训练 token 统计使用内置 whitespace tokenizer `builtin-whitespace-1`，不是特定大模型 tokenizer；正式训练前需锁定目标 tokenizer 和版本。
- 预训练混合比例配置已保留在 Build 快照边界，但本轮没有实现跨领域配额求解器；当前按来源分组和过滤结果输出。
- RAG 结构感知切分保留章节和定位，但没有语义模型、表格单元格解析或公式 AST 级边界保护。
- 评测候选目前支持人工/结构化录入；没有接入可信 LLM 生成服务，不能据此证明模型质量。
- 发布接口仍沿用开发身份机制；正式 OIDC、生产密钥和生产容量不在 P1-B。
- Playwright 与验收脚本运行于隔离本地 Docker，未访问生产环境。

## 本地复现

```bash
make init-env
docker compose --env-file .env -f infra/compose.yaml up -d
docker compose --env-file .env -f infra/compose.yaml run --rm init
uv run --locked pytest -q
uv run --locked python scripts/verify_p1b_products.py
cd apps/web && npm run typecheck && npm run lint && npm run build && npm run e2e
```

## P1-C 依赖建议

进入 P1-C 前，应先确定正式身份/OIDC、产品级配额和混合比例策略、目标 tokenizer、评测数据审核工作台、对象交付策略，以及 RAG 在线服务所需的向量库和检索接口。P1-B 本轮到此停止。
