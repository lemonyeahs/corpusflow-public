# P1-D 质量反馈与重工闭环

结论：真实 API/数据库/Worker/MinIO 闭环通过；本次重工用于验证版本与血缘机制，未虚构内容改良。

## 一次实际执行

| 对象 | 实际引用 |
|---|---|
| 原始 Asset | `95745922-a673-445a-82db-b2a3bc6ea185` |
| 原查询 Trace | `0d6abbcc-c57e-43ea-828a-fc135843f49a` |
| 原 Segment | `78826b20-4a46-4b08-b9d9-3f0ba8ab09d4` |
| Feedback | `c6abac4c-dda0-4e5d-aacc-4660a7641166` |
| QualityIssue | `a52e86a8-8599-4dc0-8550-75d2c5dfeda8`，最终 `resolved` |
| 原 PipelineRun | `5eb63e7f-d2df-4400-960a-f51164a9cb16` |
| 原 DocumentVersion | `699b0990-23e9-401a-82e4-c1a7e9a138be` |
| 新 DocumentVersion | `8fadc304-aa9b-46d5-b547-0ef1f103f34e` |
| 新 DatasetVersion | `85e606a3-bb73-4e06-be15-b90095028f4a` |
| 新 IndexVersion | `6411d5cc-1784-406e-915b-50444e6e4e55` |
| 重评 EvaluationRun | `67abfcb7-1911-41c3-8544-2748b1e0ba86` |
| 固定 Suite SHA | `8102d2cd5bf1ff60d8843b8620a9df54288fc28a940d61600b07346cc4cb885b` |

脚本提交 chunk 类反馈及修复建议，服务端验证 Segment 确实属于当前 Trace；创建既有 QualityIssue，并将允许重工的原 Run 置为 awaiting_review。未审核直接恢复返回 409。独立 reviewer 以 approved_for_rework 审核后，仍需显式调用 resume；Worker 真正重新处理原对象字节，生成新的 DocumentVersion、Segment 和中间产物。

新 Segment ID 与旧集合不相交。随后重新执行 RAG Builder、候选审核、发布 v3、异步建索引，再对原 Suite 运行 BM25 评测。原 DatasetVersion 的哈希与重工前已记录的索引输入 SHA 相同；完成索引/Trace/Suite/评测的数据库 UPDATE 被拒绝。

## 评测证据继承规则

Worker 仅为同一 Document、相同内容哈希且相同原文位置的片段增加 `reprocessed_equivalent` 边。评测再次核对同 Asset 和内容哈希后映射参考 Segment；没有使用文件名、相似字符串或不受控人工替换。
本次 v3 评测记录了 28 条按案例统计的等价引用（多证据问题可能计两条）；具体映射在每个 CaseResult。该计数不是去重 Segment 数。

若清洗/切分真的改变了参考证据内容，不能自动继承正确答案；原固定集保持证据缺失/失败，需专家重新核对并另建 Suite，对新旧集不能直接声称指标提升。

## 反馈 API 与状态保护

- 命中反馈：trace_id + segment_id + category + note；category 区分 source/parser/cleaning/chunk/lineage/retrieval/reranker/generation，note 保存复核说明和修复建议。
- 遗漏证据反馈：额外传 evaluation_run_id 和 case_id，服务端验证 CaseResult 的 trace_id，并只允许该固定案例的参考 Segment；不能随意绑定别的资料。Web 在失败案例选择后提供遗漏 Segment 输入。
- 复核、驳回、恢复使用原 QualityIssue/Run API，未另造审核状态机。终态 rejected/isolated/resolved 问题不允许再次审核；反馈不能将 rejected/isolated/running/queued Run 打开为 awaiting_review。
- 来源级保守隔离：存在未解决 QualityIssue 的资产内容不参与新查询，旧 Trace 的可见正文也被屏蔽；实际审查不只靠隐藏按钮。
- 血缘从反馈 Segment 可追到 DocumentVersion/Run，并通过现有节点/日志查询 NodeRun。全部 NodeRun ID 保存在机器证据中。

## 测试和限制

`scripts/verify_p1d_rag.py` 实测未复核恢复被拒、审核后 Worker 重工、不同版本/新索引/同集复测、当前和历史查询撤权屏蔽。`tests/unit/test_rag_policy.py` 以真实关系行覆盖用途隔离、禁用成员、质量隔离、四种不可重开状态；`p1-d.spec.ts` 覆盖真实 Web 查询、评测历史、反馈和窄屏。

本次未发现需要实际修正的论文内容，所以重工前后内容等价，不把“新版本已创建”写成“召回质量提升”。当前反馈按资产阻断而非只隔离单一 Chunk；对纯检索参数建议也复用这个保守流程，自动策略调优未实现。

生成模型未接入，生成错误分类只是可追踪反馈类型，不代表模型错误自动检测已实现。新 RAG Worker 强制终止和长期队列压力测试 NOT RUN。

复现命令：`.venv/bin/python scripts/verify_p1d_rag.py`。完整引用和查询样例见 [P1-D_EVIDENCE.json](P1-D_EVIDENCE.json)，测试配置来自 `tests/fixtures/p1d/corpus.json`。
