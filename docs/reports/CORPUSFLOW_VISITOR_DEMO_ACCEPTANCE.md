# CorpusFlow 真实数据工程可视化与交流演示验收

日期：2026-10-26
结论：**CONDITIONAL PASS（开发/演示环境）**

## 范围结论

| 模块 | 结论 | 证据 |
|---|---|---|
| P0-A 资产总览 | PASS | 真实聚合 API、workspace 隔离、空状态与 Stage 2 实测值 |
| P0-B 三栏对照 | PASS / PARTIAL | 真实签名原件、Markdown、JSON、Segment；浏览器 PDF 预览依赖内置能力 |
| P0-C 流水线质量 | PASS | 真实 Run/NodeRun/DAG/日志/配置展示，后端状态为准 |
| P1-D 案例展示 | PARTIAL | 动态案例 API；当前 workspace 缺少完整历史 KEM 链 |
| 真实公网采集 | BLOCKED | 安全门控拒绝当前解析地址，未放宽策略 |
| 真实专家评测 | NOT RUN | 没有真实专家参与证据 |

## 测试证据

- 后端：`.venv/bin/pytest -q`，103 passed、6 skipped。
- 静态检查：ruff PASS；mypy PASS（51 个源文件）；OpenAPI 契约 PASS。
- 前端：typecheck、lint、build PASS。
- 完整 Playwright 真实 Docker 回归：12 passed、1 failed；受影响的 P0-H、P0-I、responsive 共 3 passed。
- Docker `/ready`：HTTP 200；API、Worker、Dispatcher、PostgreSQL、Redis、MinIO 正常运行。

完整 Web 回归仍保留一个采集安全场景失败：`verify_p2_collection.py` 在 `/collection/plans` 返回 HTTP 409、错误码 `ACQUISITION_URL_REJECTED`。这是安全阻断证据，不能通过放宽 DNS/SSRF 检查来改成 PASS。

## 生产前置条件

正式 OIDC/SSO、网络出口与许可审查、复杂版面/数学/中文 OCR 代表性基准、真实专家标注、完整灾备/RPO/RTO、负载与依赖漏洞治理仍需完成。当前提交只包含本地代码和文档，不访问生产、不远程 push、不覆盖 V3.1 原型或历史发布。
