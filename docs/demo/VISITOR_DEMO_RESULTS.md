# 现场演示结果

日期：2026-10-26。开发服务真实运行：API、Worker、Dispatcher、PostgreSQL、Redis、MinIO 均为 Docker 服务；`/ready` 返回 HTTP 200。

## 已验证

- 工作台总览读取真实 workspace 聚合；Stage 2 workspace 实测 Source 2、Asset 2、物理文件 2、独立内容 2、总字节 1407、PDF 2、DocumentVersion 4、Segment 7。
- 资产三栏对照读取真实 MinIO 原件和 Markdown/JSON 产物。
- 处理中心展示真实 Run、NodeRun、DAG、配置和日志时间。
- 前端 typecheck、lint、build 通过；后端 pytest 103 passed、6 skipped；ruff/mypy/OpenAPI 通过。
- 完整 Playwright 真实 Docker 回归修复标题回归后为 12 passed、1 failed；失败是采集场景的 `ACQUISITION_URL_REJECTED` 安全阻断。

## 未通过或未执行

- 全套 Web E2E 中采集场景仍因安全校验返回 `ACQUISITION_URL_REJECTED`，保持阻断；没有关闭 SSRF 门控。
- 当前 workspace 没有完整 KEM 反馈重工链，页面显示 `MISSING`。
- 真实专家评测、复杂专业 PDF 全覆盖和生产环境认证/灾备不在本次演示证据中。

这些状态是现场讲解的一部分，不应改写成成功结果。
