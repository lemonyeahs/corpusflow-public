# P2-B 计划与资源门禁

真实生成与检索解耦；授权后读取当前证据，验证结构化引用；保存 Provider、Prompt、Token/成本与 Trace；建设多人标注和分歧复核。未获付费调用授权不调用付费 Provider。

已完成独立引用闭集校验器和边界测试；未完成真实模型/Reranker、持久化生成和专家工作流。专家缺席不等于工作流代码已完成。

实际增量：0014 append-only RetrievalReview，复用 RetrievalTrace 与现时授权过滤；Web/API 完成检索证据人工评分与分歧。真实 LLM/Reranker 尚无可用服务，评分范围不扩展为不存在的回答质量。
