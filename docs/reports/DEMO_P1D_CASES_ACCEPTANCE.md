# P1-D 真实案例与 RAG 反馈重工展示验收

日期：2026-10-26
状态：**PARTIAL / HONEST STATUS**

## 实现

- 新增 `GET /api/v1/demo/cases`，按当前 workspace 动态查找最新处理链及历史 KEM 反馈重工链。
- 历史案例只有在 Trace、Segment、Feedback、PipelineRun、DocumentVersion、DatasetVersion、IndexVersion 和 EvaluationRun 均真实存在时才显示 `AVAILABLE`；否则显示 `MISSING`。
- Evaluation 指标只从真实 `RagEvaluationRun.report` 读取，接口标明来源；不返回硬编码 Recall/MRR/Precision。
- Web“技术交流演示”页展示案例状态、真实对象 ID、指标来源、限制和跳转入口。

## 现场验证

当前 `p0h-admin` 空 workspace 的最新处理链为 `NOT_AVAILABLE`，历史 KEM 案例为 `MISSING`。切换到 Stage 2 workspace 后，最新处理链为 `AVAILABLE`；历史 KEM 链仍为 `MISSING`。这表示页面诚实反映当前 workspace 数据，不把别的 workspace 的历史记录串入展示。

## 测试

- Demo API live 调用：PASS（零数据和有数据 workspace 均返回可诊断状态）。
- `p1-d.spec.ts`：通过真实 Docker 后端。
- Full Web E2E 修复标题回归后为 12 passed、1 failed。采集安全场景仍因 `ACQUISITION_URL_REJECTED` 保持失败/阻断，详见最终报告。

## 限制

当前开发数据库中没有完整的历史 KEM 反馈重工链，页面不能宣称完成 P1-D 案例演示。真实公网采集和真实专家/生产模型效果也不属于本轮可证明范围。
