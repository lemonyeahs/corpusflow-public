# CorpusFlow 最终演示结果

日期：2026-10-25。开发/演示已实现范围 CONDITIONAL PASS；完整 P2 未通过。运行过程没有新增外部模型调用、没有覆盖原型或历史发布。

## 实际执行

- 后端全量 **109 passed、0 skipped**；Web 全套 **13 passed、0 skipped**，含真实 P0/P1 回归；新增页面补充复验 2 passed。
- 类型、Lint、构建、OpenAPI、Alembic 检查通过；无缓存 Docker 构建成功。当前 schema `0018_blind_review`。
- 公网资源采集 **BLOCKED**；安全拒绝不会显示成采集完成。自建 HTTPS 成功入库是独立的受控验证，不能替代公网链路。
- Worker 在实际 INSERT 时强杀，自动重投从 0 恢复 26 行。数据库恢复及单对象恢复通过；完整生产灾备未验证。

## 当前演示记录

| 项目 | 实际标识/结果 |
|---|---|
| 版面 Asset | `22e1343b-842e-4370-84c6-db244f988982` |
| 原件 SHA-256 | `be765a6e43c686dc5553297b37f5a94d82190ed3a92ad770f4e69232a286ed04` |
| 版面 Run | `0a30ad2f-7d28-40e5-81d0-433638a85c90`，`succeeded` |
| 文档版本 | `ae9a7200-c99d-4be1-8b2d-8f5f608a66fb` |
| 片段数 | 7；实际坐标见 runtime evidence |
| 盲评任务 | `0326a918-0f9d-4c37-9e82-e70241c25db1` |
| 盲评快照 | `5b82329d346a78e24ec9c9c460c7492f84ed9e287979d227980d95e9d6b0ecc4` |
| 标注 | 2 案例×2 合成测试评测员，4 条不可变评分 |
| 专家 | NOT RUN；测试分数不作专家结论 |
| 模型调用 | 本轮 0；历史已用 2/10，512 输出 Token/次上限 |

这些是不同测试空间的独立链路，**没有宣称上述版面 PDF 已经过四类发布、回答和专家评分的单一链路**。完整 Web 发布演示另由 p0-h/p1-b 等用例实际执行。旧模型回答来自获准的自制语料，不来自公网下载或新 PDF。

## 真实页面与产物

- [多栏 PDF 实际解析页面](closure_evidence/layout-web.png)：显示真实文件哈希、版本、左右栏顺序与血缘入口。
- [窄屏独立评分页面](closure_evidence/blind-review.png)：原文证据、当前本人评分、不可覆盖提交及测试标记。
- `../reports/P2_CLOSURE_ANNOTATION_SAMPLE.json`：真实 Web 下载的冻结标注，不含会话 Token。
- `../reports/P2_CLOSURE_RUNTIME_EVIDENCE.json`：实际 Run/Asset、恢复、受控采集、原型哈希和测试汇总。
- `../reports/P2_CLOSURE_PARSER_EVIDENCE.json` 与 `closure_parser_outputs/`：28 次执行及全部原始输出，失败保留。
- `../reports/closure_logs/`：实际通过的命令输出。初次失败原始日志仍保留于本机 `.local/closure/`。

测试确认：刷新恢复、异步状态、实际下载 SHA、逆向血缘、角色/用途/跨空间拒绝、授权撤销、原件和历史版本不覆盖。未做新的生成效果对照；供应商金额未知，NOT_MEASURED。

## 未演示为成功的内容

正常公网采集、专业数学二维结构/合并表格拓扑、中文复杂 OCR、真实专家独立评测、正式身份和生产灾备均无完成证据。对外展示应同时说明这些边界，不将 DEMO、流程评分、组件连通或 HTTP 202 当作业务成功。
