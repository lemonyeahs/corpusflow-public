# P3-A DPO 数据集验收

日期：2026-10-26
结论：**CONDITIONAL PASS（开发/演示环境）**

## 已实现

| 能力 | 状态 | 证据 |
|---|---|---|
| PreferenceSample / PreferenceAnnotation 持久化 | PASS | 0019_dpo_preferences + 0020_dpo_import_idempotency，workspace/sample/request 唯一键，标注不可变触发器 |
| 候选导入 | PASS | POST /api/v1/dpo/preferences/import；真实 Source、Segment、training grant 校验 |
| 多人标注与冲突 | PASS | A/B、tie、uncertain、both_invalid；冲突保留为 uncertain |
| 审核职责分离 | PASS | 导入者和标注者不能审核；未解析偏好不能通过 |
| DpoBuilder | PASS | DpoBuilder.build_preferences，输出 dpo.v1 CandidateSample |
| 质量与授权门控 | PASS | 复用质量评估、证据链、training grant 和发布门控 |
| 不可变发布 | PASS | 复用 staging、Manifest、MinIO、DatasetVersion 和下载权限 |
| Web 页面 | PARTIAL | DpoPage 真实调用 overview/import/annotation/review/build API；专门 DPO Playwright 尚未加入 |
| DPO 训练 | NOT IMPLEMENTED | 本轮明确不包含训练器或效果声明 |

## 真实 Docker E2E

在 workspace ced1fe46-2b67-4684-91d5-0e52ff83bdf4 使用真实训练授权和 Segment 完成：

- 冲突 fixture：PreferenceSample bc9a5db6-51f3-4774-9c0b-f9026c0adaa5，两位身份选择 A/B，先进入 uncertain；同一参与标注者审核返回 409。随后由第三位 reviewer 选择 A 完成复核，状态转为 approved，未覆盖任何已发布版本。
- 合格 fixture：PreferenceSample e340a00b-1c74-4e60-a443-35c900aeb76a。
- Dataset：82aa0439-ff3d-4a0d-9766-5a074e2b753f。
- Build：902d7d85-433f-4bdd-aa23-88efc109b13f，1 条候选，验证通过。
- DatasetVersion：52e7bd41-ad78-474b-9bd7-e1aeb7ed9eaf，Manifest dpo.v1，样本数 1。
- JSONL 实际字节 739；Manifest SHA-256 与对象 SHA-256 均为 9b9a940790d3132fc50ab1d998b40598f01fc09115f46e0dcfa0f09ae3ab22ab。
- 下载授权返回短期有效 300 秒；对象内容由本地 MinIO 读取并校验为 1 行 DPO JSONL。
- 血缘包含 PreferenceSample → CandidateSample → DatasetVersion，以及 Segment → PreferenceSample。
- 同一 `request_key` 重复导入返回同一 PreferenceSample 且 `idempotent: true`；不同请求体复用该键会返回 `IDEMPOTENCY_KEY_REUSED`。

## 自动化检查

- .venv/bin/pytest -q：108 passed，6 skipped。
- DPO 单元与 OpenAPI 契约：6 passed。
- ruff：PASS；mypy：PASS。
- Web typecheck、lint、build：PASS。
- Docker API/Worker/Dispatcher 重建后 /ready：HTTP 200。
- Alembic 当前版本：0020_dpo_import_idempotency。

## 未完成与风险

真实密码学专家参与、正式盲评统计、自动模型候选生成、TRL/Hugging Face 训练格式的版本化适配和训练效果验证尚未完成。外部模型调用仍遵守既有预算，未新增付费调用。公网采集的既有 DNS/SSRF 阻断保持不变；完整 P2/生产门禁仍不能标记 PASS。
