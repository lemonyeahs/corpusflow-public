# P2-B 模型回答与人工评测

结论：PARTIAL / BLOCKED，未通过完整阶段门禁。没有发现可用的生成模型与学习型 Reranker，已询问本地服务信息；未获得外部费用授权，不调用付费服务。未伪造回答、模型调用、专家身份或评分。

## 已实现

- `answer_contract.py` 验证证据闭集、实际 Segment ID、引用必须来自本次可见原文、低证据拒答及额外字段拒绝。它是结构约束组件，尚未接入真实生成，不证明语义忠实度或提示注入安全。
- 新增 `retrieval_reviews`，迁移 0014。评测员、Trace、Rubric 版本、支持性、完整性、无关证据、无答案预期、说明和时间持久化。数据库触发器禁止覆盖历史记录。
- `POST /rag/reviews`、`GET /rag/traces/{id}/reviews`：用途撤销时拒绝查看/提交相关评测，workspace 与 reviewer/admin 权限由后端执行；请求键幂等，同键不同评分冲突；多人记录并保留分歧，汇总采用每位评测员最新记录，不把多次评分当作多人。
- Web 支持证据评分、历史记录和分歧。明确显示「仅检索证据；未生成回答不评估；专家资质未验证」。测试中的两位身份是开发测试账号，不是真实专家参与。

## 实际验证

- 全量 pytest：74 passed、0 skipped，包含真实 PostgreSQL 迁移、MinIO、OCR、Embedding；`phase-b-pytest.log`。
- API 工作流：两身份评分、重复请求、冲突、工程师越权、跨空间访问全部 PASS，`scripts/verify_p2_reviews.py`。
- Playwright：1 passed，2.7 秒，提交评分与刷新后历史恢复；`review-playwright.log`。
- 前端 typecheck/lint/build PASS；ruff、mypy、契约和迁移纳入最终回归。
- 早期一次 OpenAPI 快照未更新导致契约测试失败；导出新 Schema 后全量复测通过，未删断言。

## 阻塞与未完成

LLM Provider、生成 Trace、Token/费用/限流、真实学习型重排、答案正确性/完整性评分、真实专家评测与五组完整对照仍未完成。P2-A 同集真实结果可用，但不能当作生成或 Reranker 的验收。只有配置经许可的真实本地服务、补齐异步生成与安全回归后才能解除门禁。

回退：停用新评测页面和端点；保留已写评测历史。0014 downgrade 会删除新评测表，须先导出并备份，不自动执行。
