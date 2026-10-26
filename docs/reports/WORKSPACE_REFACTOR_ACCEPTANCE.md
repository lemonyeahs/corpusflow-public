# CorpusFlow 工作台重构验收记录

## 范围

本次修改针对真实 `apps/web` 与 `apps/api` 工程，保留历史数据库表、授权、质量、发布、评测和验证服务。前端导航收敛为数据资产、数据加工、数据产品和平台管理四组入口。

## 已交付

- 侧边栏移除受控采集、交流演示、质量审核、发布下载、盲评任务和下游验证入口。对应后端路由、表和服务未删除。
- 总览新增 PDF、MD、JSON、HTML、TXT、DOCX、CSV、其他八种真实格式统计卡片。统计来自 workspace 范围内的 `Asset` 与 `AssetBlob`，展示数量、字节数、解析成功/失败和最近上传时间；空格式显示 0。
- 格式卡片可以进入资产中心并携带格式筛选。
- 上传控件支持多文件及常见文本/文档格式。登记时服务端按文件签名、MIME 和内容启发式识别格式，生成待确认元数据候选。
- 新增 `DocumentMetadata` 与 `MetadataProposal` 模型和非破坏性迁移 `0021_metadata_proposals`。候选、来源、置信度、确认人和时间均可追踪。
- 新增元数据候选查询、修改、确认和重试接口。确认前候选不会写成正式业务元数据，确认动作写入审计记录。
- SFT 数据集页面增加真实物化样本浏览，服务端分页读取 `DatasetVersionSample` 与 `CandidateSample`；无样本时显示空状态。
- 数据集列表补充版本数、最新版本和样本数；DPO 页面继续读取真实 `PreferenceSample` 及其审核状态。

## 主要 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/dashboard/overview` | 总览及 `format_stats` |
| `GET` | `/api/v1/assets?file_format=pdf` | workspace 资产与格式筛选 |
| `GET` | `/api/v1/assets/{asset_id}/metadata-proposals` | 候选及正式元数据 |
| `PATCH` | `/api/v1/assets/{asset_id}/metadata-proposals/{proposal_id}` | 修改候选字段 |
| `POST` | `/api/v1/assets/{asset_id}/metadata-proposals/{proposal_id}/confirm` | 确认并写入正式元数据 |
| `POST` | `/api/v1/assets/{asset_id}/metadata-proposals/{proposal_id}/retry` | 重新提取 |
| `GET` | `/api/v1/datasets/{dataset_id}/samples` | SFT 物化样本分页检索 |

## 元数据提取范围

当前默认使用本地 `builtin-metadata` 解析器，不调用外部模型或第三方 API。支持文件签名识别、MIME 修正、文件大小、文件名、标题启发式、作者/摘要/DOI/年份正则、语言粗判和业务类型候选。PDF 复杂版面、扫描件 OCR、Crossref/GROBID 和 LLM 补全仍依赖现有处理流水线或后续显式配置；未知字段保持为空，候选必须人工确认。

## 验证结果

- `npm --prefix apps/web run typecheck`：通过。
- `npm --prefix apps/web run lint`：通过。
- `npm --prefix apps/web run build`：通过，Vite 生产构建完成。
- Python `compileall`：通过。
- `.venv/bin/python -m pytest -q`：通过，109 passed，6 skipped。
- `.venv/bin/ruff check ...`：通过。
- `npm --prefix apps/web run typecheck`：通过。
- `npm --prefix apps/web run lint`：通过。
- `npm --prefix apps/web run build`：通过。
- `make check`：通过（Ruff、格式检查、mypy、104 个非集成测试通过，11 个集成测试按标记跳过）。
- `npm --prefix apps/web run e2e`：执行到 4 个用例后中断，2 passed、1 failed、1 interrupted、9 did not run。失败用例仍断言已移除的旧导航「SFT 产品」；另一个登录总览用例在当前本地服务状态下未找到总览标题。该结果未标记为通过。
- 隔离数据库迁移验收：未执行；当前数据库未处于最新迁移状态，未对现有数据卷做升级或清理。

## 已知限制

1. 元数据候选目前在登记请求内同步生成；大文件和扫描 PDF 仍应由既有 Worker/OCR 流程处理。
2. 重试接口通过对象存储重新读取原始对象；对象存储不可用时返回失败状态，不影响原始资产安全保存。
3. SFT 样本浏览依赖已经物化的 `DatasetVersionSample`；没有真实物化样本时不会生成演示数据。
4. 本次未删除旧页面文件，只移除了工作台入口，以保留后端能力和历史访问兼容空间；旧入口不再被导航引用。
