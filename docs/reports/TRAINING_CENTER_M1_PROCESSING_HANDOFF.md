# M1 processing handoff

状态：Agent 3 处理模块交付候选，等待集成负责人注册只读路由并执行隔离环境联调。

## 路由注册请求

在 `create_app` 注册一次：

```python
from corpusflow.api.v1.processing_insights import router as processing_insights_router

app.include_router(processing_insights_router)
```

该 router 已包含 `/api/v1` 前缀，不能再额外添加前缀。接口为：

- `GET /api/v1/pipeline-runs/{run_id}/summary`
- `GET /api/v1/pipeline-runs/{run_id}/steps/{step_id}/comparison?record_id=...`
- `GET /api/v1/pipeline-runs/{run_id}/export?export_format=jsonl|markdown|csv|txt`

每个接口先通过 `actor_id`、`workspace_id` 查询当前成员，再按运行所属 workspace 过滤。对比没有持久映射时返回 `404 COMPARISON_NOT_AVAILABLE`；失败或未完成运行导出返回 `409 INVALID_STATE_TRANSITION`；超过 `training_center_max_records` 或 `training_center_max_bytes` 在发送响应前返回 `413 EXPORT_LIMIT_EXCEEDED`。

## 数据库迁移

`0023_processing_evidence` 增加：

- `node_runs` 的步骤单位、输入/输出引用、修改/失败计数、开始/完成时间；
- `segments.record_key`，用于跨版本保留逻辑记录键；
- `processing_record_maps`，保存具体 attempt 的 before/after segment 映射和内容哈希。

Worker 在解析和三个内置清洗算子完成后写入这些字段。失败步骤不会把未知计数写成零，也不会把最终版本引用复制到其他步骤。

## 交接约定

- Agent 2 可直接调用 `serialize_records(records, record_kind, export_format)`；返回 `SerializedExport(chunks, content_type, extension)`，UTF-8，支持 `jsonl/markdown/csv/txt`。
- Agent 4 可从 `NodeRun.input_refs/output_refs` 和 `processing_record_maps` 构建有执行依据的步骤节点；重试 attempt 使用独立 `NodeRun.id`。
- 接入页的导出范围是当前选中的单文件运行，页面不会把它标为整个批次。
