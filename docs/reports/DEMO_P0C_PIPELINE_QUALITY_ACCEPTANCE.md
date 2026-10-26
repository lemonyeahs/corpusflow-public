# P0-C 流水线与质量可视化验收

日期：2026-10-26
状态：**REAL / PASS（读取既有持久化运行数据）**

## 实现

- `GET /api/v1/pipeline-runs/{run_id}` 现返回持久化 DAG。
- Web 处理中心展示 PipelineRun、NodeRun、状态、真实创建时间、输入/输出统计、失败原因、执行日志和节点配置 JSON。
- 页面从后端状态刷新，不把 202 Accepted 显示为处理完成；审核等待、失败和成功状态保留原有状态机语义。
- 新增真实 Demo API 可列出当前 workspace 中可核验的处理链案例；缺少历史对象时返回 `MISSING`，不会复制固定样例。

## 真实证据

在 Stage 2 workspace 读取到 2 个 Asset、4 个 DocumentVersion、7 个 Segment 和 3 个 Run（`succeeded:2`、`awaiting_review:1`）。节点状态和配置来自数据库，不是前端生成。

## 测试

- 后端 pytest：103 passed，6 skipped。
- ruff：PASS；mypy：51 个源文件无错误。
- P0-H、P0-I、responsive Playwright：3 passed。
- Worker/Outbox/解析回归由既有全量测试覆盖；本轮未修改其业务状态机。

## 限制

当前页面展示已有执行记录和日志，尚未增加独立的时间序列图、实时 WebSocket 推送或大规模分页节点日志。质量指标仍以已有质量 API 为准，不能从“运行成功”推断内容质量合格。
