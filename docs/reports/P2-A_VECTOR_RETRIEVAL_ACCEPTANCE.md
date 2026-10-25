# P2-A 向量检索验收

结论：开发环境 CONDITIONAL PASS。真实模型、持久化索引、异步构建、授权撤销、增量复用、语义混合和 Web 已接入；pgvector/HNSW、大规模负载尚未实现。本报告替代此前仅离线组件试验的 PARTIAL 记录，保留其原始负面结果。

## 实现与范围

- 独立 `tools/semantic/uv.lock`，sentence-transformers 6.0.1；本地 Apache-2.0 MiniLM，384 维，CPU；无模型下载、随机向量或付费调用。
- EmbeddingAdapter：本地端点白名单、禁止重定向/环境代理、超时/有限重试、响应维度及归一化校验、模型和 tokenizer 文件联合 SHA。
- `0013_semantic_embeddings` 给 RagChunk 增加 embedding。原 PostgreSQL 无 vector 扩展，采用有界精确余弦，未替换数据库或历史索引。
- API `POST /rag/indexes` 增加 embedding；查询/评测增加 vector、semantic_hybrid、min_similarity。RRF 常数 60。用途与质量先过滤，Trace 查询重新授权。
- Worker 原子事务、重复投递无重复 Chunk；新版本相同内容/模型复用向量，测试复用 26/26。失败可用新请求键重新构建；保留失败记录。索引模型、输入哈希、维度、耗时、用量冻结；已成功索引禁止修改。
- Web 支持索引类型、向量/混合策略、阈值、分项分数。

## 同集真实结果

31 条冻结查询，27 条有答案、4 条无答案，Top-3。来自真实 MinIO 发布文件、PostgreSQL Chunk、Celery Worker 和本地模型。

| 策略 | Recall | Precision | MRR | nDCG | 无答案误命中 |
|---|---:|---:|---:|---:|---:|
| BM25 | 1.000 | 0.346 | 1.000 | 1.000 | 1/4 |
| 向量，无拒答阈值 | 1.000 | 0.346 | 0.938 | 0.954 | 4/4 |
| 向量，阈值 0.5 | 0.778 | 0.272 | 0.778 | 0.778 | 0/4 |
| BM25 + 向量 RRF | 1.000 | 0.346 | 0.981 | 0.986 | 1/4 |

没有全面改善；阈值降低误命中同时丢失答案。合成小评测集不能代表密码学真实论文全集。`P2-A_PLATFORM_EVIDENCE.json` 保存全部逐条指标、配置、Trace 和实际延迟。一次构建约 208 ms，26 个向量的 float32 原始数值为 39,936 字节（不是 JSONB 磁盘占用），输入 505 Token、截断 0，外部调用费用 0，本机算力费用未测量。

## 验证

- `EMBEDDING_ENDPOINT=http://127.0.0.1:58110 .venv/bin/pytest tests/integration/test_embedding.py -q`：1 passed，实际中英文语义及模型不匹配拒绝。
- `.venv/bin/python scripts/verify_p2_semantic.py`：PASS，持久化、重复消息、增量复用、同集评测、不可变、撤权后当前及历史结果过滤。
- 首次用既有 Web 反馈资产建立索引，实际返回 QUALITY_GATE_FAILED；保留失败索引，改建全新测试空间后通过，未放宽门控。
- 前端 typecheck/lint/build PASS；迁移 upgrade/check PASS，完整 upgrade/downgrade/reupgrade 由 PostgreSQL 集成测试覆盖。
- Playwright 及最终全量统计见最终报告，避免将运行中测试提前记为通过。

## 限制和回退

本机服务未容器化、仅回环监听，不是生产模型网关；精确搜索上限 5,000，模型 128 Token 之后截断并报告；共享测试集并无独立验证集，0.5 不是经过泛化验证的阈值。强杀恢复在最终独立故障测试中单独记录。关闭 embedding 配置即可继续词法查询，旧文件和版本不变。数据库列回退有向量丢失风险，须先备份并停用新增索引，不自动 downgrade。

阶段复测：全量 pytest **73 passed，0 skipped**（独立迁移库、真实 MinIO、实际 OCR/Embedding）；`make check` PASS，66 个非集成测试；P2-A Playwright **1 passed**（25.8 秒）。原始日志保存在 `.local/p2/phase-a-pytest.log`、`phase-a-check.log`、`vector-playwright.log`。所有新模型测试均使用实际模型响应。
