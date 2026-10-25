# P2-A 向量检索阶段记录

状态：PARTIAL，**未通过平台集成门禁**。

本地 MiniLM 实际离线 CPU 推理成功：Apache-2.0 模型卡；快照 e8f8c211226b894fcb81acc59f3b34ba3efd5f42，384 维。权重 SHA-256 eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b。没有模型下载、随机向量或付费 API。

新增 tools/semantic/benchmark.py，以冻结 P1-D Suite 的同一组问题、证据映射执行真实向量 Top-3。实际结果：Recall 1.0、Precision 0.345679、MRR 0.938272、nDCG 0.954143。无阈值 Top-K 的无答案误召回率为 1.0，比词法基线更差；不隐瞒该退化。

本轮推理环境借用已有本地 Python 环境中的 sentence-transformers 6.0.1，尚未建立项目内独立锁定部署，因此不能宣称可复现容器服务已交付。运行使用 HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1，命令与模型路径可用 --model-dir/--output 指定。输出原始指标在 .local/p2/vector-benchmark.json。

未完成：EmbeddingAdapter 平台接入、持久化向量表与迁移、真实 pgvector、Worker 增量恢复、向量授权撤销复验、语义混合及 Web。现有 PostgreSQL 不提供 vector 扩展，不能替换共享数据库来凑测试。离线组件试验不是 IndexVersion/MinIO 平台验收。
