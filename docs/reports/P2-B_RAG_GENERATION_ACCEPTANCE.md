# P2-B 证据回答、语义重排与人工评测验收

日期：2026-10-25。结论：**已实现范围 CONDITIONAL PASS；完整阶段 PARTIAL**。真实回答、重排与人工评测工作流已接入；真实专家参与和完整生成质量评测尚未完成。本文替代早期“无模型服务、仅引用校验组件”的状态说明。

## 实际实现

- GenerationAdapter：兼容 Chat Completions、JSON 输出、无工具、提示版本 `closed-evidence.v1`、温度 0、45 秒超时、HTTP 重试 0。检索与生成解耦，Outbox/Celery 执行，队列仅传业务 ID。
- 0016 新增 GenerationRun，0017 保护终态结果、冻结配置和已消耗的调用预留。提供商并发锁串行执行；数据库全局预算持久化，失败与超时也消耗额度。崩溃后调用结果不明时标记 `GENERATION_CALL_OUTCOME_UNKNOWN`，不自动重复计费。
- 生成前、响应后、读取历史时检查 workspace、成员和现时用途授权。只允许显式配置的自制 fixture 工作空间外发；无证据直接拒答，未配置服务不生成假回答。
- 引用须来自当前可见检索结果，Segment 与原文引文校验，拒绝额外输出字段、不完整输出、工具调用和报告超限的输出。引用校验不等于语义可靠性证明。
- 独立 RerankerAdapter 使用真实本地 MiniLM bi-encoder 余弦相似度，对最多 50 个召回候选重新排序。保留召回分数、原始名次、独立重排分数、模型版本和 Token。它不是 Cross-Encoder；未伪称接入专业重排模型。
- 0014 RetrievalReview 不可覆盖，支持证据与回答两种评分对象、回答正确性、支持性、完整性、无依据回答、无答案预期。答案评分必须关联同一 Trace 的已成功回答或拒答。检索汇总与回答评分分开，保留多人及历次记录；专家资质标记 NOT_VERIFIED。
- Web 提供真实生成状态轮询、引用/血缘、历史答案、语义重排开关、评分与分歧查看。202 只显示排队状态。

## API 与数据库

| 接口 | 行为 |
|---|---|
| POST /api/v1/rag/answers | 创建异步回答，engineer/admin、授权 workspace、请求键幂等 |
| GET /api/v1/rag/answers/{id} | 现时用途授权后查询真实状态、结果、配置、用量 |
| POST /api/v1/rag/reviews | reviewer/admin；检索或回答评分，不允许覆盖历史 |
| GET /api/v1/rag/traces/{id}/reviews | 评分历史、分歧及独立回答评分 |
| POST /api/v1/rag/queries、/evaluations | semantic_rerank 参数，兼容原有词项重排 |

0016/0017 升级、降级、重升级、模型比对已在独立临时 PostgreSQL 执行。实际现有回答上尝试修改终态、重置调用预留、删除记录均被数据库拒绝，事务回滚。证据见 `P2-B_ANSWER_REVIEW_EVIDENCE.json`。

## 授权和真实模型结果

用户授权仅自制测试语料、最多 10 次、每次最多 512 输出 Token。实际调用 **2 次**，其余为本地检索、已保存结果读取或无证据直接拒答。密钥仅保存在被 Git 忽略且权限为 0600 的本地配置，不进入代码、报告或浏览器。

服务是用户提供的外部兼容端点，不能从返回模型名推断厂商或真实模型来源。请求格式参考 [Chat Completions 官方接口](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)，第三方支持情况以下列实测为准。

| 样本 | 结果 | 外部调用 | 输入/输出 Token | 延迟 |
|---|---|---:|---:|---:|
| 自制 AES 问题 | succeeded，128 bits，引用原文 “Its block size is 128 bits.” | 1 | 360 / 59 | 8292 ms |
| 自制文档中的提示注入 | refused：insufficient evidence | 1 | 312 / 15 | 1562 ms |
| 无证据问题 | 服务端 refused | 0 | 0 | 不适用 |

原始配置、真实结果和 Trace 见 `P2-B_GENERATION_EVIDENCE.json`。重复任务未追加调用。价格未知，货币成本 NOT_MEASURED。2 条调用不证明通用提示注入防护，也不能推断整个专业领域的答案正确率。

## 同一冻结检索集重排对照

31 条问题，27 条有答案、4 条无答案；二值相关性，来源和标签与 P2-A 相同。详细逐条结果见 `P2-B_RERANKER_EVIDENCE.json`。

| 方法 | K | Recall | Precision | MRR | nDCG | 无答案误命中 | p50/p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 3 | 1.000 | 0.346 | 1.000 | 1.000 | 1/4 | 4.24 / 5.12 |
| BM25 + 语义重排 | 3 | 1.000 | 0.346 | 1.000 | 1.000 | 1/4 | 33.52 / 55.94 |
| 语义混合 + 重排 | 3 | 1.000 | 0.346 | 0.981 | 0.986 | 1/4 | 53.53 / 101.61 |
| 语义混合 + 重排 | 5 | 1.000 | 0.207 | 0.981 | 0.986 | 1/4 | 56.34 / 77.97 |

本次没有证明重排质量提升；延迟增加，混合排序 MRR 低于词法基线，扩大 K 降低 Precision。保留所有负面结果。完整 31 问题的 LLM 对照 NOT RUN，不能以检索指标代替回答质量。

## 验证与复现

```sh
.venv/bin/python scripts/verify_p2_reranker.py
.venv/bin/python scripts/verify_p2_answer_reviews.py
npm --prefix apps/web run e2e -- tests/p2-generation.spec.ts
```

回答复验只读取已保存的原始 fixture：`scripts/verify_p2_generation.py` 使用固定请求键，存在结果时不会新建调用。不要删除预算/回答记录或更换工作空间来绕开上限；全新部署必须重新取得范围和费用授权后才运行真实生成。

最终 pytest **92 passed**，包括调用预算、外发拒绝、撤权、引用闭集、评分对象、幂等与跨空间规则。真实 API 回答评分/不可变数据库保护 PASS；Web 答案、引用、拒答与评分 PASS，仅读既有真实模型结果。完整 Web 回归 11 passed，新增评分断言另复验 1 passed。静态、契约、迁移均 PASS，完整命令见总验收。

## 未完成与回退

真实领域专家参与 NOT RUN；测试账号评分仅验证工作流。独立专业 Cross-Encoder、真实全量回答评测、语义忠实度判断、多提供商/生产限流均未验收。需要专家和经授权的更大评测预算，不能替用户补造标注。生成供应商返回的模型身份和 Token 用量尚无独立证明。

停用 LLM_PROVIDER、移除 LLM_WORKSPACES 即停止新生成，不删除既有历史。迁移回退会删除回答/评分或去除保护，应先停写、导出并备份；本轮没有对业务库执行 downgrade。旧数据集、原型及发布对象不变。
