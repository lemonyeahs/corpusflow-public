# 玄知大模型现场演示指南

本指南面向本地开发/演示环境。先启动 `make init-env`、`make up`，确认 `curl -i http://127.0.0.1:58000/ready` 返回 200，再启动 `npm --prefix apps/web run dev -- --host 127.0.0.1`。演示只使用隔离 workspace，不使用生产凭据。

## 建议顺序

1. 登录并确认 workspace。
2. 打开“工作台总览”，说明 Source、Asset、物理文件、独立内容、DocumentVersion、Segment 的计数单位。
3. 在资产列表打开一个真实 Asset，进入“PDF / Markdown / JSON 对照”，展示哈希、来源、签名原件和定位片段。
4. 打开“数据处理中心”，展示 PipelineRun、NodeRun、DAG、状态、参数和日志。强调 202 只代表已接受。
5. 在数据产品页面查看真实 DatasetVersion、Manifest、下载和血缘。
6. 打开“技术交流演示”，只展示状态为 `AVAILABLE` 的案例；`MISSING`、`NOT_AVAILABLE` 和 `BLOCKED` 必须照实说明。

## 讲解边界

不要把空 workspace 的零值改成示例数字，不要把 MockAdapter、入队状态、签名 URL 或运行成功说成内容质量合格。复杂公式、合并表格、中文 OCR、公网采集、真实专家评测和生产认证仍需单独验收。
