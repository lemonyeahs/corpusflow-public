# P0-F Lineage/UI 对接验收

日期：2026-10-24（Asia/Shanghai）  
任务：TASK-CF-006。范围：FR-001/004/007/043、AC-LINEAGE、AC-DASH、TC-24/27/28。

## 实现

- `lineage_edges` 持久化 Source→Asset→DocumentVersion→Segment→CandidateSample→DatasetVersion 关系。
- `GET /api/v1/lineage/{object_type}/{object_id}` 按 workspace 双向查询，返回 relation 和 as_of；审计 API 受 admin 授权。
- OpenAPI 快照同步更新；V3.1 HTML 保留为只读原型，业务 API 不修改原型状态。

## 实测

- `scripts/verify_business_loop.py`：发布候选后从 CandidateSample 反查存在血缘边；跨 workspace 查询受 403 隔离；审计事件在 API 中可查。
- `uv run --locked pytest -q tests/unit tests/contract`：`12 passed`；`ruff`、`mypy` 通过。

## 结论与边界

P0-F 门禁通过，P0-B～P0-F 最小业务闭环完成。正式 Web UI API Adapter、Playwright E2E、统计仪表盘和 P1 RAG/外部适配仍未完成，不能把 V3.1 原型标为真实生产 UI。
