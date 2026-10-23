# CorpusFlow V3.1 · 缺陷修复、专业能力增强与回归测试

版本：V3.1（2026-10-23）  
基线：`CorpusFlow_V3.html` / `CorpusFlow_V3_CHANGELOG.md`  
独立产物：`CorpusFlow_V3_1.html`  
测试实现：`CorpusFlow_V3_1_playwright_tests.py`；结果：`CorpusFlow_V3_1_TEST_RESULTS.json`

> **性质：单 HTML 本地交互原型，而非真实数据平台。** 上传/导入、解析/清洗、模型生成、质量评分、登录/角色、RAG、发布以及任务恢复都是浏览器内存中的模拟状态机。没有真实后端认证、许可自动核验、分片上传、对象存储、WeKnora/Data-Juicer 调用或模型推理。刷新页面后状态复位。所有种子文档及授权均为演示记录，不代表真实文献许可证结论。

## 一、功能实现状态矩阵

| 能力 | V3.1 状态 | 具体交互或限制 | 真实后端依赖 |
|---|---|---|---|
| 总览 KPI / 分布 / 质量覆盖 | 本地交互 | 可交互 Asset/Segment/Release 口径；候选/待获取不计入原始 Asset 数 | 元数据汇总查询、异步统计 |
| 原始资料登记 | 本地模拟 | 本地文件选择，仅登记元数据和批次；不上传内容与真实计算哈希 | 上传服务、对象存储、病毒校验 |
| URL / DOI / AI 资料发现 | 本地模拟 | 明确区分候选、待获取计划与已登记资产；不执行真实网络采集 | 采集连接器、版权许可核验 |
| 用途级许可证 / 数据门控 | 已修复的本地模拟 | `research`、`training`、`rag`、`evaluation` 四个用途分别授权；默认拒绝未授权用途 | 许可台账、政策决策点、审计 |
| 原始数据资产批量处理 | 已修复的本地模拟 | N 份选择形成一个处理批次和 N 个独立 Run，保留 Asset ID 映射 | 队列、Worker、事务与幂等 |
| 不同流水线模板 DAG | 增强的本地模拟 | PDF、HTML、专利、结构化清洗、SFT 候选各有独立节点、参数和输入输出 schema；可保存本地参数修订 | 流水线定义服务、算子注册/执行 |
| 节点执行统计及失败诊断 | 增强的本地模拟 | 节点耗时、输入输出数量、过滤量、版本、失败原因、日志以及原文/清洗后对照 | Run/NodeRun、Artifact、Log 数据源 |
| 质量审核 → 恢复执行 | 已修复的本地模拟 | Pending/Rejected/Isolated 阻断；Reviewed-ready 需要单独恢复并执行才会关闭异常 | 后端状态机、审核事件、Worker resume |
| 结构化资产 / 血缘追踪 | 本地演示 | 关联 Source、Asset、Document Version、Segment、Sample、Dataset Version | 血缘关系表、不可变产物 |
| SFT / Pretrain / RAG / Eval 构建 | 增强的本地模拟 | 类型专属样本字段、用途许可检查；DPO 仍仅展示格式 | 生成/去重/审核/导出服务 |
| 构建快照与版本发布 | 已修复的本地模拟 | 绑定构建输入版本、配置和候选；变更阻断旧快照发布；Manifest 记录校验结果及非加密 DEMO 签名 | 配置版本、数据库事务、内容哈希、Manifest |
| 角色与职责分离 | 已修复的本地模拟 | 工程师可构建但不能发布；审核员可审核但不能构建；发布管理员独立发布；禁止同一用户自审自发 | 真实 IAM / RBAC / ABAC / 审计 |
| 查询驱动的 RAG 验证 | 已修复的本地模拟 | 查询文本驱动本地关键词匹配；无关查询返回零命中，不编造答案和引用；检索还检查 RAG 用途许可 | 混合检索、向量库、Rerank、LLM、评测 |
| 系统集成配置 | 接口占位 | WeKnora、Data-Juicer、LLM、存储等全部标明未连接 | 集成适配器、秘钥管理、健康检查 |

## 二、八项原有业务缺陷及修复结果

| 编号 | V3 根因 | V3.1 修复 | 验证结果 |
|---|---|---|---|
| DEF-01 授权误判 | 种子文件 `authorized: true` 自动被映射到 `training`，`内部研究` 被错误视作可训练 | 用显式 `usages` + `licenseStatus` + `resourceState` 决策；`SRC-0002` 仅拥有 `research`；不再信任历史 `authorized` 布尔值 | PASS：研究/训练/RAG/评测独立检查 |
| DEF-02 批量仅处理首份 | `selectedAssets[0]` 生成唯一任务 | 为每个被选 Asset 创建独立 Run，同时生成 `PBATCH-*` 关联 Run ID / Asset ID | PASS：2 份产生 2 个独立 Run；附加 3 份检查产生 3 个 Run |
| DEF-03 RAG 与查询无关 | 查询前固定按“差分/密码分析”返回结果 | 保存本次 query + hits 快照，按查询信号与片段匹配并检查 RAG 许可；零命中时拒绝生成证据答案，修改查询清空旧结果 | PASS：天气查询 0 条、密码分析查询非空、修改查询使快照失效 |
| DEF-04 驳回后可恢复 | resume 仅拦截 `pending`，忽略 `rejected` | 所有未闭环异常默认阻断，只有 `reviewed_ready` 可恢复，恢复之后需逐节点执行并更新产物 | PASS：驳回无法恢复；通过审核仍不立刻产生新产物 |
| DEF-05 发布权限过宽 | 数据工程师拥有 `publish`，候选审核和发布边界不完整 | 工程师去掉 `publish`，增加独立发布管理员；候选记录审核人，发布强制不同审核身份，所有修改动作继续做本地授权拦截 | PASS：只读/工程师/审核员/发布管理员多角色检查 |
| DEF-06 不分产品用途授权 | 所有构建统一读取 `training` | SFT/Pretrain=`training`，RAG=`rag`，Eval=`evaluation`，DPO 仍结构展示；筛选与发布都按目标用途校验 | PASS：仅 RAG 授权来源可进入 RAG，不可进入 SFT / Eval |
| DEF-07 候选计入原始资产 | URL、AI 确认后调用文件元数据登记，尚未下载便增加 Asset 数 | 引入 `discoveryCandidates`、`ingestPlans`；发现/待获取不建 Asset；必须另外登记原始文件才增加 Asset 数 | PASS：创建 URL 获取计划前后 `docs.length` 不变 |
| DEF-08 构建与发布快照不一致 | 构建后可改 `dsConfig`，旧候选仍允许用新条件发布 | 保存构建 config、入选 Segment/Document Version、生成类型及候选；变更条件失效；发布重新校验用途、质量、来源分组、schema、审核身份及输入版本；版本复制样本内容形成不可变演示快照 | PASS：修改领域导致门控失败；发布后修改候选不改变旧版本 |

## 三、数据对象与状态约束

**资源阶段**：`Discovery Candidate（候选资源）` → `Ingest Plan（待获取）` → `Asset（已登记的原始资料记录）`。本地登记的 Asset 仍是**元数据占位**，未拥有真实持久化内容。已登记原始资产数量不以检索发现结果、任务计划数量或待下载 URL 计数。

**独立用途授权**：`licenseStatus=已确认` **且** `usages.includes(targetPurpose)` 才允许对应用途，尚未核实、缺失证据或仅内部研究均不能推定允许训练。V3.1 演示中部分种子明确配置了多项模拟授权；它们不是根据“允许训练”自动推出其他真实使用权。

**质量状态机**：`pending / rejected / isolated` → 阻断；`reviewed_ready` → 允许恢复但仍是未完成；任务节点执行完成后 → `resolved` 并更新新 Artifact、Document Version、Segment。驳回不是审批通过，也不产生自动执行结果。

**构建与发布快照**：`Build ID` 保存 `config + selectedSegmentIds + inputs(document_version_id, source_id) + candidates + checks`；发布时重新核对 Config、产品特有 Schema、来源实际用途、源质量问题、候选复核和分组划分。版本 Manifest 保存构建引用、输入池、实际引用片段、质量门控和 `DEMO-*` 非加密签名。`DEMO-*` 不是正式内容签名算法。

**最小角色权限示意**：

| 角色 | 查看 | 接入 | 处理 / 构建 | 质量 / 候选审核 | 发布 | 系统配置 |
|---|---|---|---|---|---|---|
| 只读用户 | ✓ | — | — | — | — | — |
| 数据工程师 | ✓ | ✓ | ✓ | — | — | — |
| 数据审核员 | ✓ | — | — | ✓ | — | — |
| 发布管理员 | ✓ | — | — | — | ✓ | — |
| 管理员 | ✓ | ✓ | ✓ | ✓ | ✓（同人自审自发仍禁止） | ✓ |

切换角色会映射到不同的**演示身份**，便于进行审核人与发布人分离的演示。因浏览器本地状态可被开发者工具修改，以上不构成真实安全认证或访问控制。

## 四、专业数据工程展示增强

- **流水线模板**：不同模板配置独立 DAG，包含 Ingest、Router、Parser、Transform、Cleaner、Quality Evaluator、Exporter 等节点。单节点展示业务作用、输入与输出、参数 JSON、修订版本、执行统计。参数变更仅写本地模板，不改变已创建 Run 的参数快照。
- **处理实例**：单次 Run 保存独立模板引用与参数快照，可定位来源 Asset、批次 ID、逐节点日志、虚拟耗时、输入输出和过滤统计，失败原因与清洗前后片段对照。
- **质量和覆盖率**：新增结构化片段元数据完整率、可用片段数、专业领域覆盖与来源数量；构建预览保留命中数、排除理由、可用 Tokens 及原始来源配比。数值均由演示数据计算，不能作为真实模型质量结论。
- **产品专属 Schema**：SFT 为 `messages + evidence_ids`，Pretrain 为 `text + source_id`，RAG 为 `chunk_id + content + page + metadata`，Eval 为 `question + reference_answer + evidence_ids`，DPO 尚无真正的候选生成实现。
- **数据集配比**：按来源 ID 分组分配 Train/Validation/Test，Manifest 记录源组数量。小样本源组不足时阻断；RAG 采用 index 分组，不套用训练样本比例。
- **RAG**：根据本次查询和已授权片段做简单规则检索，展示相关片段、分数（模拟）、来源页码、溯源入口。未命中时返回明确“无证据”，不编造回答。

## 五、Playwright 测试记录

工具：**Playwright Python + headless Chromium**，载入交付 HTML 原始内容 `page.set_content`，运行了真实 DOM 选择、点击、填写、角色切换，并断言前端状态和页面输出；另检查 `pageerror`。测试文件和 JSON 结果可重复运行（需要系统有 Playwright + Chromium）。

| 场景 | 正常 / 异常 | 预期 | 实际 |
|---|---|---|---|
| 许可：内部研究不可训练 | 异常门控 | research 不推导 training/rag/evaluation | PASS |
| 资产批量处理 | 正常 | 2 份选中，2 个独立 Run | PASS |
| 质量审核驳回 | 异常 | rejected 后无法 resume/advance | PASS |
| 审核通过→恢复→完成 | 正常 + 许可边界 | reviewed_ready 不直接成功，完成后仍无训练授权 | PASS |
| 无关 RAG 查询 | 异常 | 0 命中、不编造来源和答案；修改查询清旧结果 | PASS |
| URL 发现 / 待获取 | 异常统计 | 创建获取计划，Asset 数不增长 | PASS |
| 本地文件元数据登记 | 正常 + 权限边界 | 增加元数据记录，但研究阅读不等于训练许可 | PASS |
| 角色身份切换 | 正常 | 审核员与发布管理员使用不同演示身份 | PASS |
| 四种产品独立门控与 Schema | 正常 + 异常 | SFT/Pretrain/RAG/Eval 使用各自许可与字段 | PASS |
| 构建配置修改后发布 | 异常 | 新领域条件使旧构建门控失效 | PASS |
| 角色 RBAC 与职责分离 | 异常 | 只读/工程师/审核员等越权动作被阻断 | PASS |
| 发布快照不变性 | 正常 | 记录的 Build、输入、门控、样本一致；候选后续修改不改旧版本 | PASS |
| 各模板 DAG / 参数 | 正常 | 切换模板节点数量不同，可保存 JSON 参数 | PASS |
| 390px 移动宽度 | 布局 | 不产生严重全局横向溢出 | PASS |

**最终结果：14 / 14 通过，0 条最终回归失败。** 初轮自动化中三个步骤因测试 locator 同时命中侧栏和看板卡片而触发 Playwright strict-mode 歧义，修正为侧栏按钮精确定位后已重跑通过；该问题属于测试脚本，不是业务组件的执行失败。

**测试限制**：此运行环境的浏览器管理员策略阻止 `file://` 导航（`ERR_BLOCKED_BY_ADMINISTRATOR`），因此未宣称验证了所有操作系统和浏览器的本地文件双击打开行为。已通过 `page.set_content` 直接执行 HTML 中两个内联脚本，脚本通过 `node --check` 语法检查。真实后端/海量负载/并发写入/权限安全/真实文档解析未进行测试。

## 六、技术组件复用决策（建议，尚未接入）

| 组件 | 复用定位 | 适合的边界 | 本期实现状态 |
|---|---|---|---|
| WeKnora / docreader | 文档解析能力适配 | PDF/OCR、文档版面和解析产物；不要用其知识库对象代替统一的 CorpusFlow 原始资产模型 | 仅接口入口 |
| Data-Juicer | 数据清洗、过滤、去重算子 | 将算子运行封装为有配置快照、输入输出、指标和日志的任务节点，平台负责统一任务生命周期和治理 | 仅算子配置示意 |
| LLM 推理/生成服务 | 候选问答、证据辅助校验 | LLM 生成仅形成候选，质量审核、版权授权与发布门控必须独立 | 未连接 |
| 对象存储 S3 / MinIO | 不可变原始文件与大产物 | 多段上传、哈希、保存、版本链接 | 未连接 |
| PostgreSQL + 搜索 / 索引 | 元数据关系、来源血缘、检索索引 | 权限上下文、关联 ID、事务与检索分页 | 未连接 |
| 任务执行组件（队列/Worker） | 执行实例与 DAG 调度 | 节点超时、重试、幂等、人工复核挂起与恢复 | 未连接 |
| 检索与 Rerank 服务 | RAG 验证 | 按工作空间和授权过滤后召回，再重排、引用、评测 | 未连接 |

**推荐原则**：优先复用成熟的解析与处理算子，但保留 CorpusFlow 自己的 Source/Asset/Segment/Run/Build/Release 元数据与状态机，不将某个第三方项目的数据结构强行当成平台主模型。

## 七、后端接口及依赖关系

| 接口（建议） | 前置依赖 / 权限 | 输出和不变量 | 优先级 |
|---|---|---|---|
| `POST /api/v1/discovery-candidates` / `POST /ingest-plans` | 采集连接器；ingest 权限 | 候选/待获取记录，不产生 Asset | P0 |
| `POST /api/v1/uploads/init` / `complete` / `POST /assets` | 对象存储、哈希、病毒校验；ingest | 已持久化 File → Asset，幂等 ID | P0 |
| `GET /api/v1/assets` / `stats` | Source/Asset 元数据，workspace 权限 | 与检索分页和计数口径一致 | P0 |
| `GET/POST /api/v1/pipelines` / `POST /pipeline-runs/batches` | Pipeline DAG、Worker、process | 一批 N 个 Asset 对应 N 个 Run 与独立结果 | P0 |
| `GET /api/v1/pipeline-runs/{id}/nodes` / `resume` | 事件日志、质量审核状态、process | 审核驳回不能恢复；成功前需要实际产物 | P0 |
| `GET /api/v1/documents` / `segments` / `lineage` | Parser、Artifact Store、血缘表 | Segment → Document Version → Asset 关系稳定 | P0 |
| `POST /api/v1/quality/issues/{id}/reviews` | 审核员权限、状态版本乐观锁、审计 | Review 事件与 Run 恢复分离 | P0 |
| `POST /api/v1/authorization/check` | 许可证台账 / policy engine；用途与来源 | 明确 `allowed=false` 默认拒绝，逐用途评估 | P0 |
| `POST /api/v1/dataset-builds/preview` / `POST /dataset-builds` | 结构化片段、授权、质量、process | 不可变输入快照 / Config / 候选引用 | P0 |
| `POST /api/v1/dataset-builds/{id}/validate` / `POST /datasets/{id}/versions` | review/publish 权限、质量/证据/泄漏门控、数据事务 | 版本 Manifest 与构建快照、实际样本一致 | P0 |
| `POST /api/v1/rag/search` / `feedback` | 已授权 RAG 索引、召回、Rerank | 查询绑定证据，不命中则不伪造引用 | P1 |
| `POST /api/v1/auth` / `GET /roles` / `/audit` | 服务端 IAM，工作空间 | 最小权限与审计可核验 | P0（上线前） |
| `/api/v1/system/integrations` | Secret Store、服务监测 | 状态为真实探测结果而不是前端猜测 | P1 |

推荐按 **Source/Asset → IngestPlan/Batch → PipelineRun/Artifact → Segment/QualityIssue → DatasetBuild → DatasetVersion → RAG/Eval** 的依赖顺序推进；身份授权、审计和用途许可证决策应作为横切能力。

## 八、已知限制与下一阶段清单

### 已知但尚未解决（不能作为正式后端能力验收）

1. 许可证状态、独立用途授权及审核人仍是可修改的前端模拟信息；没有真实法律许可核验或服务端隔离。
2. 上传只登记元数据，无法校验文件字节、保存原始 PDF、计算真实哈希、完成批量异步执行。
3. DAG 节点耗时、质量分、Tokens 为演示统计，缺少 Worker 实际测量、吞吐、CPU/GPU/内存指标。
4. 数据集 Manifest 的 `DEMO-*` 签名仅用于演示，不是密码学安全的 SHA-256 或签名，也没有持久化/事务级不可变保障。
5. RAG 采用有限关键词规则，没有真实 Embedding、混合召回、相关性标注、Reranker 或 LLM；不能把示例分数作为 Recall/Faithfulness 结论。
6. 仍未实现真实数据集 JSONL/Parquet 导出、多租户服务端权限控制、异步作业负载/并发测试、完整公式/表格 OCR 准确性评测、数据集重复度与来源泄漏检测。
7. 模拟参数配置允许在浏览器内修改模板；真实运行应将模板版本和不可变执行配置作为独立数据库实体，并阻止未经审批的生产配置漂移。

### 下一开发阶段建议

- **P0-1：授权与资产模型**：定义 per-purpose grant、license evidence、Source/Asset/Discovery 对象、迁移与严谨统计口径，接入真正的认证、权限和审计。
- **P0-2：真实处理闭环**：上传/文件对象存储 → 解析适配 → 任务队列 → 节点日志与产物 → 质量异常审核 → 可重试/恢复。
- **P0-3：数据集交付闭环**：结构化查询与按来源分组 → SFT / Pretrain / RAG / Eval 构建 → 审核门控 → 不可变 Manifest → JSONL/Parquet 导出。
- **P1-1：RAG 真实验证**：授权过滤、混合检索、Rerank、答案引用、检索指标与反馈回流。
- **P1-2：可运维规模化**：真实质量/覆盖率指标口径、数百万级检索分页、性能与资源统计、操作审计与容灾。

## 九、使用与复测

1. 直接使用支持的浏览器打开 `CorpusFlow_V3_1.html`，进入本地演示。浏览器权限可能影响 `file://` 部分操作，但页面不依赖外部网络资源。
2. 重点试用：原始资产勾选两份 → 批量独立任务；选择 ISSUE-001 驳回 → 不可恢复；创建 SFT → 修改配置 → 旧任务不可发布；切换审核员/发布管理员 → 正确授权后发布；查询无关 RAG 问题 → 无命中。
3. 测试复跑：`python CorpusFlow_V3_1_playwright_tests.py`（需要 `playwright` Python 包和本机 Chromium；根据实际机器位置调整脚本中 Chromium 与 HTML 路径）。
4. 不要将模拟质量、许可证、发布结果引用为真实项目数据或正式验收指标。
