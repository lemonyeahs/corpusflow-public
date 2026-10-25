# P1-D 检索评测基准

日期：2026-10-25。数据源是原创合成密码学技术说明，许可证 CC0-1.0；不是公开论文评测榜单。所有指标由真实 PostgreSQL/MinIO/Worker 检索结果计算。

## 固定数据与标注

- fixture：`tests/fixtures/p1d/corpus.json`，SHA-256 `c5dd4d281d24ad53c36b70d45664afdbcf1751bfb3708ba894177ed755f6eb4c`。
- 实际 HTML 输入 SHA：`4a804b45eb920436e310d3c9118d021deae29e86fe4641ce502d5d9e159aef23`；Asset：`95745922-a673-445a-82db-b2a3bc6ea185`。
- Suite：`c669e2da-9afd-4846-8257-d05057ed4680`，SHA-256 `8102d2cd5bf1ff60d8843b8620a9df54288fc28a940d61600b07346cc4cb885b`。
- Evaluation 发布版本：`9b6a6aaf-2240-4237-8b35-f9e32d032336`；开发审核身份 `db1f77e6-7654-4f2a-8c85-2ab5faeb9aa7`。
- 26 个事实/定位问题 + 1 个 AES/SHA 多证据问题 + 4 个明确无答案问题，共 31 个不同问题。另有 API 级跨空间、无 RAG 用途和撤权断言，不混入检索效果分母。
- 包含英文缩写、SHA-256 output length 术语改写、中英文、模运算和参数表定位。参考答案/证据由代理根据原创 fixture 编写；**领域专家核对 NOT RUN**。

## 指标口径

| 指标 | 计算方式 |
|---|---|
| Recall@3 | Top-3 中唯一相关 Segment 数 / 参考相关 Segment 数，再对 27 个有答案问题宏平均 |
| Precision@3 | Top-3 中唯一相关 Segment 数 / 3；不足 3 条也以 3 为分母 |
| MRR | 第一个相关 Segment 的实际原始排名倒数；重复片段不压缩名次 |
| nDCG@3 | 二元相关标签 grade=1，增益 2^grade−1，log2(rank+1) 折损；按参考列表理想 DCG 归一化 |
| Hit | 至少一个相关 Segment 被召回的比例，分母 27 |
| 无答案空召回率 | 4 个无答案问题中 hits=0 的比例；这是检索拒答代理指标，不是 LLM 回答正确率 |
| 延迟 P50/P95 | Worker 内单次 retrieve 的墙钟耗时，最近秩百分位；含查询与授权 SQL，不含排队/浏览器传输/模型生成 |

重复 Chunk 对同一 Segment 只计一次相关命中。参考标签可定位到实际发布候选的 SampleEvidence。指标手算和重复排名边界测试见 `tests/unit/test_retrieval.py`。

## 实际结果

| 数据版本 / Chunk 数 | 检索方案 | Recall@3 | Precision@3 | MRR | nDCG@3 | Hit | 无答案空召回率 | P50 / P95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1.0.0 / 26 | fts | 0.7407 | 0.2469 | 0.7407 | 0.7407 | 0.7407 | 1.0000 | 2.386 / 11.683 |
| 1.0.0 / 26 | bm25 | 1.0000 | 0.3457 | 1.0000 | 1.0000 | 1.0000 | 0.7500 | 1.936 / 3.452 |
| 1.0.0 / 26 | hybrid | 1.0000 | 0.3457 | 1.0000 | 1.0000 | 1.0000 | 0.7500 | 3.711 / 6.771 |
| 1.0.0 / 26 | hybrid + 词项重排 | 1.0000 | 0.3457 | 1.0000 | 1.0000 | 1.0000 | 0.7500 | 1.912 / 2.833 |
| 2.0.0 / 29 | bm25 | 1.0000 | 0.3457 | 1.0000 | 1.0000 | 1.0000 | 0.7500 | 1.710 / 2.559 |
| 3.0.0 / 26 | bm25 | 1.0000 | 0.3457 | 1.0000 | 1.0000 | 1.0000 | 0.7500 | 1.817 / 2.581 |

上述六个实验均使用同一 Suite SHA 和 K=3。v1 为 chunk_size=128、overlap=0；v2 为 12/2；v3 为复核后重工、128/0。Chunk 参数单位是 P1-B 的 `builtin-whitespace-1` tokens；检索分词另使用 `unicode-cjk-bigram-latin-v1`。中文无空格文本的 Chunk token 计数存在既有局限，不能当作模型 tokenizer。

FTS 使用 PostgreSQL simple 与 plainto_tsquery（全部词项匹配），BM25 使用真实授权集合词频/长度，RRF 常数 60。可选重排使用查询词项覆盖率。原始分数、融合值、重排前后排名分别保存，不作为概率。Embedding、生成模型为 null；token_cost=null 表示未执行模型，不能解释为已测得零成本。

## 失败样本与解释

### v1.0.0 / fts

- `KEM encapsulation`：Trace `cf0c5662-b85b-44f8-bbb1-24c0a761ce1b`；hit=0.0，no_answer_correct=None。
- `密钥`：Trace `bf85bb32-767f-4bbb-8d4f-5dd8409eb24f`；hit=0.0，no_answer_correct=None。
- `SHA-256 output length`：Trace `4d649604-3631-4428-b2c4-73ee25cc52a6`；hit=0.0，no_answer_correct=None。
- `授权`：Trace `7d4c428b-3301-47e7-909a-611bfbd8993b`；hit=0.0，no_answer_correct=None。
- `AES 密钥`：Trace `b19c101e-d332-4368-ab14-4f7af6f49d60`；hit=0.0，no_answer_correct=None。
- `穷举`：Trace `2bc46e72-8134-442a-b5ad-e97e8f8705e9`；hit=0.0，no_answer_correct=None。
- `AES SHA-256`：Trace `a9fae874-8cc9-40ab-a302-93e805f194f3`；hit=0.0，no_answer_correct=None。
### v1.0.0 / bm25

- `AES inventor favorite coffee`：Trace `34cd876d-96f8-47fc-bf41-091b14da3e8c`；hit=None，no_answer_correct=0.0。

BM25/RRF 在这一小型说明集上召回更全，但 `AES inventor favorite coffee` 仅因 AES 词项仍会召回片段，无答案空召回率为 3/4。系统给出 LOW_EVIDENCE 或词法结果，generation 始终 NOT_CONFIGURED，不产生咖啡偏好等捏造回答。FTS 的严格交集拒绝这个问题，同时漏掉部分中文/改写/多证据问题。

v2 实际变成 29 个 Chunk，但本次指标未改善；词项重排也未改善。v3 的精确等价重工保持指标，验证可复测性，不代表数据质量得到提升。禁止用本组 27 个有答案问题的高召回推断真实论文、同义词、公式推理或模型问答效果。

## 版本与证据

| 版本 | DatasetVersion | IndexVersion | EvaluationRun |
|---|---|---|---|
| 1.0.0 / fts | `44c0442f-2ac2-4dea-8710-74148177912a` | `e857b9f6-1375-4a76-ab00-5efeebfc71ce` | `e69e6ec4-27e7-474a-919e-7827cc5b7499` |
| 1.0.0 / bm25 | `44c0442f-2ac2-4dea-8710-74148177912a` | `e857b9f6-1375-4a76-ab00-5efeebfc71ce` | `fd6377f1-2284-4448-9657-03d385df031c` |
| 1.0.0 / hybrid | `44c0442f-2ac2-4dea-8710-74148177912a` | `e857b9f6-1375-4a76-ab00-5efeebfc71ce` | `dee6e904-d1cb-453f-a12d-c033c93def6c` |
| 1.0.0 / hybrid | `44c0442f-2ac2-4dea-8710-74148177912a` | `e857b9f6-1375-4a76-ab00-5efeebfc71ce` | `4a2c23d6-d4ad-46c6-aa3d-6308b79439ae` |
| 2.0.0 / bm25 | `aaac89af-8cad-4252-b13b-25b477ed9cdb` | `875e8a92-a719-41a2-8a7b-7cc4de213ea0` | `c0e5027f-2b40-480d-8a83-062062bf6564` |
| 3.0.0 / bm25 | `85e606a3-bb73-4e06-be15-b90095028f4a` | `6411d5cc-1784-406e-915b-50444e6e4e55` | `67abfcb7-1911-41c3-8544-2748b1e0ba86` |

机器可读摘要、完整 31 条参考标注、实际查询/分数与失败案例见 [P1-D_EVIDENCE.json](P1-D_EVIDENCE.json)。完整逐案例结果保存在 PostgreSQL `rag_evaluation_runs.report` 和本机 `.local/p1d/evidence.json`，未复制会话 Token。

复现：先启动真实 Docker 栈，运行 `.venv/bin/python scripts/verify_p1d_rag.py`。每次使用新 workspace/业务 ID，因而 Suite SHA 会随证据 ID 改变；一次实验内六种对照严格共用同一冻结 SHA。不同执行间延迟可能变化，不作显著性或吞吐声明。

## 外部方案评估

PostgreSQL 16 的 `pg_available_extensions` 无 vector，simple FTS 对“密钥轮换”的实测是整体词，而非中文分词。本轮不更换已有数据库镜像。参照 [PostgreSQL 文本检索文档](https://www.postgresql.org/docs/16/textsearch.html) 和 [pgvector 官方项目](https://github.com/pgvector/pgvector)，保留真实 Provider 接口供后续许可、模型和容量评估；当前不宣称已接入向量检索。

向量、学习型 Reranker、LLM Judge、专家回答正确性、生产规模/负载：NOT RUN。
