# 本地语义服务

独立锁文件，不将 Torch 装入 API 镜像。当前只支持管理员明确配置的本机 CPU 服务；不下载模型，不调用付费服务。

```sh
uv sync --project tools/semantic --frozen
export CF_EMBEDDING_MODEL_DIR=/absolute/path/to/approved/model-snapshot
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 tools/semantic/.venv/bin/uvicorn server:app --app-dir tools/semantic --host 127.0.0.1 --port 58110 --no-access-log
```

API/Worker 主机模式配置 `EMBEDDING_ENDPOINT=http://127.0.0.1:58110`；Docker Desktop 使用 `http://host.docker.internal:58110`。服务仅监听回环，无认证，不能暴露到公网或当作生产模型网关。端点由管理员环境配置，不接受业务请求指定 URL；客户端拒绝重定向及环境代理。

模型与 tokenizer 文件共同散列，冻结到 IndexVersion。批量 16，CPU、L2 归一化；响应记录输入 Token、实际编码 Token 与截断条数，模型最多 128 Token。更换模型或配置需新索引，不覆盖旧向量。

当前 PostgreSQL 使用不可变 JSON 向量，授权筛选后精确余弦计算，最多 5,000 Chunk。这不是 pgvector/HNSW，不适合大规模生产负载。迁移 `0013_semantic_embeddings` 仅增加可空列；回退会删除向量列，应先停用语义索引并备份，不在已有部署自动执行 downgrade。
