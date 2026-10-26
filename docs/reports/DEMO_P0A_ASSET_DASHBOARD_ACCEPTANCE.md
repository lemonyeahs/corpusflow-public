# P0-A 数据资产总览验收

日期：2026-10-26
状态：**REAL / PASS（开发演示环境）**

## 实现

- 新增 `GET /api/v1/dashboard/overview`，统计范围由后端身份和 workspace 确定。
- 支持 `source_id`、`file_format`、`asset_status`、`since`、`until` 筛选。
- 统计明确区分 Source、Asset、物理文件、SHA-256 独立内容、DocumentVersion、Segment、CandidateSample 和 DatasetVersion。
- Web “工作台总览”使用真实 API 展示原始规模、格式/业务类型分布、生命周期阶段、运行状态、质量/授权状态和最近产品版本。

## 真实证据

使用本地 Docker 数据库中的 `Stage 2 Demo Workspace` 只读验证，workspace id 为 `6691c55f-d278-4090-86bc-6311db9ab31b`。接口返回：Source 2、Asset 2、物理文件 2、独立内容 2、总字节数 1407、PDF 2、DocumentVersion 4、Segment 7、Run 状态 `awaiting_review:1` 与 `succeeded:2`，并返回 RAG 版本 1、样本 1、已发布 1。上述值来自实际接口响应，没有写入前端常量。

空 workspace `p0h-admin` 的接口返回零资产和空分布，证明没有用演示数据填充空状态。

## 测试

- `pytest -q`：103 passed，6 skipped。
- `npm run typecheck`、`npm run lint`、`npm run build`：PASS。
- Playwright `p0-h.spec.ts`、`p0-i.spec.ts`、`responsive.spec.ts`：3 passed。
- workspace 隔离通过 API 身份上下文执行；未发现跨 workspace 聚合返回。

## 限制

业务类型只使用已登记元数据，无法可靠判定时归入 `unclassified`。总览是实时聚合，当前未做预聚合；大规模数据的性能 SLA 尚未验收。资产卡片导航沿用现有列表入口，细粒度失败原因筛选仍属于后续增强。
