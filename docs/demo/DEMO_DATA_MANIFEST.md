# 演示数据清单

机器清单见 DEMO_EVIDENCE.json，由真实数据库只读导出，不是固定响应。

| 组 | 原件 | 预期与边界 |
|---|---|---|
| 正常处理 | tests/fixtures/p1a/plain_text.pdf | 仓库生成的说明 PDF；解析、清洗、去重、质量节点 |
| 异常审核 | UTF-8 字节 `this is not a PDF`，Web p0-i.spec.ts | 明确损坏失败；驳回不可恢复。没有结构化版本、发布或检索结果，不能填假记录 |
| 检索对比 | tests/fixtures/p1d/corpus.json 按 verify_p1d_rag.py 构造 HTML | CC0 原创说明；RAG/Evaluation 发布、31 查询、6 实验、反馈重工 |

这些是合成教学材料，不是专业论文，也没有领域专家签署。正常 PDF 组未独立发布 DatasetVersion；发布演示使用 P0-H/P1-B/C/D 测试产生的版本。不能把三个工作空间伪装成同一个来源链。详细数据产品和检索证据保存在 .local/p1c/evidence.json、.local/p1d/evidence.json；历史固定样例见 docs/reports/P1-D_EVIDENCE.json。
