# CorpusFlow 本轮综合验收记录

日期：2026-10-25。**整体结论：FAIL，尚未完成用户要求的 P2 全阶段交付。** 本文件记录已执行结果与真实缺口，不表示连续开发目标已完成。

## 状态矩阵

| 阶段/模块 | 状态 | 依据 |
|---|---|---|
| P0/P1 既有业务 | REAL / CONDITIONAL PASS | 本轮真实 Docker Web 与完整后端回归；保留开发认证限制 |
| P1 六组检索复现 | REAL / PASS | 31 条冻结问题、六组指标及分母一致；25% 无答案误命中未删除 |
| 系统演示 | PARTIAL | 三组原件哈希/实际 Run/NodeRun/版本清单、操作指南、真实截图；跨三组单一空间完整演示未验收 |
| P2-A 本地 Embedding | REAL 组件 / PARTIAL 平台 | MiniLM 384 维实际 CPU 推理及固定问题评测；无持久向量索引、授权集成与语义混合 API |
| P2-B 引用校验 | REAL 组件 | 严格 Schema、当前证据闭集、原文引文与低证据拒绝测试 |
| P2-B 生成/Reranker/专家 | BLOCKED / NOT RUN | 尚无授权且配置好的生成服务、学习型 Reranker、真实专家。专家工作流代码也尚未完成 |
| P2-C OCR | REAL 组件 / PARTIAL 平台 | 真正图片型 PDF、Tesseract 文字/页码/图像坐标；未接 Docker Worker/模板 |
| URL/DOI 采集 | NOT IMPLEMENTED | URL/DNS/重定向 SSRF 与 IngestPlan 流程未交付，不能开放未保护采集 |
| 生产认证/HA/备份恢复/负载 | NOT RUN | 不宣称生产就绪 |
| 全系统“采集→OCR→向量→LLM→专家→重工” | NOT RUN | 缺少多个实际环节，未使用 Mock 替代 |

## 最终运行结果

- `make check`：Ruff 全仓通过，90 个 Python 文件格式通过，Mypy 40 个源文件通过；66 passed / 6 deselected。
- `.venv/bin/python scripts/verify_p1d_environment.py`：**72 passed，0 skipped，10.89 秒**；包含真实独立数据库迁移和 MinIO、实际 OCR；1980 条既有弃用警告。
- `npm run typecheck`、`npm run lint`、`npm run build`：PASS；Vite 构建成功。
- `npm run e2e`：**7 passed，23.4 秒**；实际 Docker 服务，包含发布、下载、质量、血缘与反馈。
- `.venv/bin/alembic check`：No new upgrade operations detected；迁移仍为 0012，本轮没有业务数据库迁移。
- `scripts/verify_p1_reproducibility.py`：六组历史效果指标复现通过；不要求运行时延完全相同。
- Worker 强杀恢复：NOT RUN。旧脚本在停止前可能已经完成任务，不接受其成功输出作为强杀证据；未强杀共享 Worker。
- 远程 CI、生产、付费模型：NOT RUN；没有远程 push。

本机原始日志：`.local/p2/`。可提交组件证据：`P2-A_VECTOR_COMPONENT.json`、`P2-C_OCR_COMPONENT.json`。实际界面截图：`.local/demo/retrieval.png`；临时会话和截图未提交。未将旧原型截图作为真实 UI 证据。

## 指标与限制

真实向量 Recall@3=1.0、Precision@3=0.345679、MRR=0.938272、nDCG@3=0.954143；无阈值向量 Top-K 对四个无答案问题误召回率=1.0，弱于已有词法基线。不能只报告 Recall；这些是原创小型说明数据的检索指标，不是专业论文回答质量。模型 CPU 构建约 246 ms，仅单次小样本组件测量，非服务 SLA；货币成本未测。

OCR 实际文本为「CorpusFlow OCR evidence: AES block size is 128 bits.」，坐标单位是渲染像素，不是原 PDF 点。公式结构、复杂表格、中文、多栏及图注指标 NOT_EVALUATED。WeKnora/docreader ListEngines 实际返回可用引擎，但没有据此声称复杂文档已成功解析。

现有架构仍为 React/Vite → FastAPI → Policy/Service → PostgreSQL，Outbox/Redis/Celery 执行异步处理，MinIO 保存发布物和解析物。新增 OCR/回答校验是可独立测试的 Adapter 组件，未修改正式 API 的可用能力宣告。没有把其他项目的依赖环境描述为 CorpusFlow 锁定部署。

## 本地提交

| 提交 | 内容 |
|---|---|
| 715d402 | P1 复验及历史指标自动对照 |
| a19d1c0 | 三组真实演示清单与指南 |
| ee34c88 | 真实离线向量组件基准 |
| fc1f7d7 | 引用闭集和输出 Schema 校验 |
| 822a15b | 有界 OCR Adapter、图片型 PDF 及测试 |
| 196ae94 | 组件结果、负面案例和截图流程 |

提交粒度不等于阶段通过。P2-A/B/C 均未标记整体 PASS。

## 未完成项与顺序

1. 高：隔离 Worker 故障复验与完整演示准备；不能破坏共享环境或删除历史资料。
2. 高：把可用 MiniLM 接入独立锁定运行环境、EmbeddingAdapter、持久向量表/IndexVersion、Worker 和授权过滤；pgvector 扩展部署须保留旧数据库。
3. 高：真实生成/Reranker 资源配置及使用授权；生成 Trace、多人专家标注、费用与引用安全仍需实现。用户尚未补充模型资源，不得调用付费服务。
4. 高：OCR Docker 部署和模板接入；URL/DOI SSRF 防护、候选审核/用途证据、IngestPlan 必须先于正式采集开放。
5. 高：正式 OIDC、备份恢复、多节点/负载、安全扫描尚未验证，生产门禁不通过。

回滚仅回退本轮代码提交，不清空数据库/对象桶。新增测试数据和历史发布记录保留；V3.1 原型不变。演示重置使用新的工作空间，不覆盖旧发布版本。
