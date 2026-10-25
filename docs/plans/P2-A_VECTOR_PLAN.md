# P2-A 计划与未完成门禁

先离线验证已有 Apache-2.0 MiniLM 的实际向量，再实现版本化 EmbeddingAdapter、独立向量存储迁移、Worker 增量恢复和当前授权过滤；用同一冻结 Suite 比较词法/向量/RRF。必须锁定独立运行依赖，不能以借用其他项目环境作为部署交付。

已完成：离线推理和真实指标。未完成：平台接入、持久化索引、混合与 Web。详见阶段记录；阶段不标 PASS。

后续平台增量已完成：0013 RagChunk.embedding、独立锁定模型服务、Outbox/Worker 实际构建、精确余弦/混合 RRF、现时授权过滤、Web 和同冻结集对照。完整结果见 P2-A_VECTOR_RETRIEVAL_ACCEPTANCE；pgvector 大规模索引未实现。
