# P1 整体验收

2026-10-25，基线 81bb913。结论：CONDITIONAL PASS（开发环境）；严格故障恢复门禁尚未全部完成，不宣称生产就绪。

| 检查 | 本轮实际结果 |
|---|---|
| pytest（含 PostgreSQL 迁移与 MinIO） | 69 passed；1980 条已知弃用警告 |
| Ruff / Mypy | PASS；38 个源文件类型检查 |
| 前端 typecheck / lint / build | PASS |
| Playwright 真实 Docker | 7 passed，24.6 秒；覆盖 P0-H/I、P1-A/B/C/D 和窄屏 |
| 当前库 Alembic check | No new upgrade operations detected |
| 历史 31 问题、6 组实验复现 | PASS；新增 verify_p1_reproducibility.py 比较六项指标与分母，保留无答案误命中率 25% |
| Worker 强制终止恢复 | NOT RUN；旧 verify_worker_recovery.py 可能在停止前已完成任务，不能当作运行中崩溃恢复证据 |

真实能力包含 PDF/HTML 处理、算子流水线、四类数据产品发布、质量治理、词法检索、评测与重工。Web 回归实际调用 PostgreSQL/Redis/MinIO/Worker；不是仅依据历史报告判断。证据保存在 .local/p2 和本轮 Playwright JSON。

高风险遗留：开发身份不是 OIDC；缺少严格隔离的运行中 Worker 故障复验；复杂文档和专家评测未通过。中风险：中文词法局限、25% 无答案误命中、线性 BM25 与未测生产规模。保留原发布记录和 V3.1 原型。

P2 前置条件：核实本地模型能实际推理、明确模型许可，独立向量索引；真实 LLM 与专家资源不可伪造；没有隔离条件不停止或强杀共享 Worker。可继续演示和独立组件验证，但这些不能消除上述未通过项。


## 最终回归补充（2026-10-25）

上表为 P1 阶段当时记录。P2 最终复验已补齐严格隔离的运行中故障：在随机测试库和独立队列中观察到 Worker 阻塞于实际 INSERT 后，仅强杀自建容器；回滚后 0 行，重启后 Redis 自动重投生成 26 个唯一片段。未停止共享 Worker。见 `P2-C_WORKER_RECOVERY_EVIDENCE.json`；此项由 NOT RUN 更新为 PASS，不代表所有故障组合或生产 HA 通过。

最终全量 pytest 92 passed、0 skipped；Web 11 passed；迁移 head 为 0017，静态、契约与当前库 check 通过。P1 历史六组指标复现及负面样本保持不变。开发认证、专业标注和生产规模限制仍存在，P1 开发/演示结论维持 CONDITIONAL PASS。
