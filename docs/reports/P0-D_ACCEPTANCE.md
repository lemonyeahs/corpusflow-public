# P0-D Pipeline + QA 验收

日期：2026-10-24（Asia/Shanghai）  
任务：TASK-CF-004。范围：FR-005/006/017～025/042、AC-RUN、AC-QA、AC-STRUCT、TC-09/11～15。

## 实现

- `pipeline_templates/versions`、`processing_batches`、`pipeline_runs`、`node_runs`、`artifacts`、`documents/document_versions/segments`、`quality_issues/reviews` 和 lineage edges。
- 批量请求逐资产建立独立 Run；Run 保存配置快照/hash；内置解析器生成 DV/Segment/Artifact；审查状态由后端控制。
- `open/in_review/rejected/isolated/returned` 阻断 resume；`approved_for_rework` 仅允许显式 resume 后重新执行，审核不会直接把任务标成成功。

## 实测

- `scripts/verify_business_loop.py`：N=3 返回 3 个不同 Run；创建质量问题后 resume 返回 409 `RUN_REVIEW_BLOCKED`；审核为 `approved_for_rework` 后 resume→queued，再执行生成新成功产物。
- 迁移与静态/契约门禁同 P0-B，均通过。

## 结论与边界

P0-D 门禁通过，可进入 P0-E。Celery/Redis Outbox、租约、退避和真实 PDF/HTML 专用适配器尚未扩展；当前内置 parser 是受控基础实现，不代表外部解析器真实能力。
