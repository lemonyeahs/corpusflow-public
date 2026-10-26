# P0-B PDF / Markdown / JSON 对照验收

日期：2026-10-26
状态：**REAL / PASS（已有解析产物）；PDF 预览为 PARTIAL**

## 实现

- 新增 `GET /api/v1/assets/{asset_id}/lineage-view`，返回 workspace 校验后的 Asset、Source、原始文件签名 URL、全部 DocumentVersion、Markdown Artifact、结构化 JSON Artifact 和 Segment。
- 原始对象通过 300 秒签名 URL 访问，不返回 MinIO 永久地址或凭据。
- 结构化 JSON Artifact 不存在时明确返回 `NOT_AVAILABLE`；已有版本可返回基于数据库的 `DATABASE_VIEW`，不会伪造 Artifact 成功。
- 新增 Web“文档对照”页面，支持版本选择、三栏内容查看、页码/坐标/哈希与血缘字段展示。

## 真实证据

在 `Stage 2 Demo Workspace` 对 `plain_text.pdf` 的真实 Asset 调用接口，原始对象为 `AVAILABLE`，选定版本的 Markdown 与 JSON 均为 `AVAILABLE`，并返回 1 个 Segment 及定位信息。接口通过真实 MinIO 读取内容；后端未在响应中暴露密钥。

## 测试

- `GET /assets/{id}/lineage-view` live API 验证：PASS。
- OpenAPI 契约快照更新后 `tests/contract/test_openapi.py`：PASS。
- 前端 typecheck、lint、build：PASS。
- Asset 详情到对照页的页面路由与返回状态：已实现；完整浏览器中 PDF iframe 的跨浏览器兼容性未单独做矩阵测试。

## 限制

PDF 左栏依赖浏览器对签名对象的内置预览能力；当前没有内嵌页码导航或逐字 diff。大 Artifact 会截断到 2 MB 并保留哈希与状态。不存在产物时显示可诊断状态，不能把 HTTP 202 或数据库元数据当作解析成功。
