# 训练数据中心：并行开发任务书

状态：M0 共享基线已冻结为契约 1.0.0；见收尾报告 `../reports/TRAINING_CENTER_M0_CLOSEOUT.md`。下文 M1–M3 仍是待交付范围，不代表业务功能已经实现。

视觉基准：[HTML 交互原型](../previews/training-data-center.html)。
接口基准：[共享契约 v1](../specs/TRAINING_CENTER_CONTRACT_V1.md)。

当前团队采用两名人工负责人、四个 agent；具体映射和启动指令见[两人四 Agent 协作指南](TRAINING_CENTER_AGENT_COLLABORATION.md)。下文 A～H 保留为职责角色，以便明确模块归属，不要求配置八名实际成员。

## 1. 目标与团队配置

建议配置：7 名开发者（A～G）＋1 名测试负责人（H）。字母是负责人占位符，可直接替换为实际姓名。A 同时负责架构、共享入口及集成，每个模块只有一个最终负责人。

交付目标：训练数据中心首页、按格式的数据台、真实接入与清洗、可追溯的多跳血缘、CPT/SFT/DPO 浏览与原有构建流程。页面以独立 HTML 原型为视觉参考；静态原型中的统计数字、成功状态与处理记录不直接作为业务实现。

技术基线：现有 React / TypeScript / Vite，新增 React Router（HashRouter）、Ant Design、TanStack Query、ECharts / echarts-for-react、@xyflow/react / @dagrejs/dagre；样式使用 CSS Modules 与主题变量，保留现有 lucide-react。后端沿用 FastAPI、SQLAlchemy、Celery、PostgreSQL、MinIO。

| 人员 | 负责模块 | 可立即开始的工作 | 最终交付 |
|---|---|---|---|
| A | 应用骨架、契约、公共组件、集成 | 路由表、主题、页面挂载约定、锁文件、契约目录 | 可运行的页面壳与统一公共层，负责集成发布候选版本 |
| B | 文件数据目录、生成脚本、统计与训练数据只读 API | manifest、JSONL 数据模型、固定种子生成、查询统计 | 可复现数据包，首页/数据台/训练数据集 API |
| C | 解析、清洗、处理记录、通用导出 | 4 个解析器、3 个算子、计数口径与序列化器 | 真正执行的处理链、阶段摘要、清洗结果导出 |
| D | 血缘后端与血缘前端 | 多跳图查询模型、图组件、中文关系字典 | 多跳查询、算子实例节点、React Flow 页面 |
| E | 训练数据中心首页与数据台 | 卡片布局、统计图、筛选表格、接口样例联调 | 首页与格式数据台、文件对比、关联数据集 |
| F | 数据接入前端 | 上传与配置页面、清洗流程条、结果对比 | 接入—处理—导出完整前端流程 |
| G | CPT/SFT/DPO 前端及原有构建入口 | 共用页面框架、三类样本渲染、切分可视化 | 三类训练数据页、样本浏览、构建新版本标签 |
| H | 契约验证、端到端验收、集成环境 | 验收场景、隔离工作空间、跨页面数据核对 | 回归报告、缺陷清单、可重放验收流程 |

## 2. 先完成一个短前置，再同时启动全部模块

### M0：共享基线（A 主责，B/C/D 参与，约半天到一天的排期预算）

1. 确认共享契约中的路径、枚举、分页、统计单位、错误结构及工作空间身份。
2. A 一次性安装所有已确认前端依赖并提交锁文件；后端新增依赖也由 A 汇总更新。
3. A 建立路由壳、认证上下文、QueryClientProvider、主题作用域和公共组件的最小可用接口。
4. B/C/D 各提供一个符合契约的成功响应及空数据/错误响应；A 放到统一样例目录。
5. 建立开发专用的请求拦截层，接口样例可供前端使用。请求拦截只在显式开发配置下启用；生产构建不能自动回退到样例。
6. 合并 M0 后所有人基于同一提交创建分支；开发中缺少后端时使用同一版样例，不在页面中另写统计常量。

M0 完成条件：新页面壳能登录；hash 链接可直达；全体成员能启动并读取相同契约。此时页面可为空壳，不要求首页、解析器或血缘已经完成。

### M1：并行开发

- B、C、D 同时实现后端；E、F、G 同时以契约样例开发前端。
- D 的图布局、节点交互先使用约定的图响应；算子执行历史等待 C 接入，不阻塞图组件开发。
- B 的生成器、统计与列表不依赖 C；涉及清洗产物和算子血缘的数据包，在 C 提供处理接口后再运行真实处理链补齐。
- G 用旧构建页面的适配器完成标签页，不等待新的只读目录能执行构建。
- H 从第一天开始检查契约一致性和真实环境准备，不等功能做完才介入。

### M2：三条独立联调线

| 联调线 | 参与人 | 闭环 |
|---|---|---|
| 资产与展示 | B + E + G | 同一版本的数据文件 → 首页统计 → 格式数据台 → 数据集 → 样本与导出 |
| 接入与处理 | C + F | 上传真实文件 → 解析 → 清洗 → 真实数量/示例 → 四种格式导出 |
| 血缘与追溯 | C + D + B | 真实算子记录/生成来源 → 多跳图 → 点击节点 → 返回文件与样本 |

A 持续集成三条线；H 持续跑对应场景。无需等待某一条线全部结束才开始另一条。

### M3：统一回归与交付

A/H 共同验收路由、权限、数据一致性、旧功能回归及响应式布局，B～G 修复各自模块问题。验收不通过的模块不能仅以“页面可以打开”结项。

## 3. 文件所有权与每人的任务

下列新增路径是目标目录，不表示当前已经存在。成员只能直接修改自己负责的文件；共享文件由指定负责人提交。需要跨模块改动时，提交明确的接口请求或由双方约定独立的小 PR。

### A：应用骨架与集成负责人

独占文件：

- `apps/web/package.json`、`apps/web/package-lock.json`。
- `apps/web/src/App.tsx`、`main.tsx`、现有 `styles.css`、`components.tsx`、`types.ts`。
- `apps/web/src/api/client.ts`、`vite.config.ts`、`tsconfig.json`。
- `apps/api/src/corpusflow/main.py`、`api/v1/business.py`、`pyproject.toml`、`uv.lock`。
- `docs/api/openapi.json`（项目实际导出目标，统一由 A 执行生成）、根目录 `README.md` 与 `apps/web/README.md`。
- 如需配置路径或挂载：配置模块、`.env.example`、Compose 与 Dockerfile。

新增文件：

- `apps/web/src/app/`：路由、认证包装、工作空间上下文、QueryClientProvider。
- `apps/web/src/ui/`：主题、PageHeader、MetricCard、Panel、ChartFrame、空/错/加载状态、ExportMenu。
- `apps/web/src/contracts/training-center.ts`：共享 DTO；M0 决定使用人工维护还是自动生成，不并存两份来源。
- `apps/web/src/dev/training-center/`：共享开发样例与请求拦截入口。
- `apps/api/src/corpusflow/contracts/training_center/`：后端共享契约与数据类型；B/C/D 提交字段需求，A 统一落地。

工作：

1. HashRouter 与约定路由；保留旧页在高级分组，保留角色可见性和服务器授权。
2. 提供 `useWorkspaceContext()`，返回现有 `ApiContext`，页面无需修改登录存储。
3. 前端查询键统一包含 workspace、catalog、revision、filters；退出/换工作空间时清理旧缓存。
4. 配置 Ant Design 主题；新样式作用于 `.training-center-shell`，旧页面使用 `.legacy-page` 隔离，避免浅色改版破坏旧页面。
5. 各模块导出独立页面入口，A 负责注册，不由页面作者修改 App.tsx。
6. 新增后端路由采用独立文件，A 注册路由。为已有 business.py 的认证/db 依赖提供兼容入口，避免大家同时重构业务大文件。
7. 下载客户端单独处理 Blob/Content-Disposition；现有 `request<T>` 按 JSON 解析，不能直接用来下载文件。
8. 按当前机器可用端口启动，后端代理使用配置；不能把本机 58080 硬编码为所有环境的地址。

验收：路由刷新/前进后退正常；未登录访问保存原目标并在登录后返回；无权限路由有明确反馈；旧资产/处理/构建功能可访问；桌面和移动导航可用。

### B：数据目录、生成器与只读 API

独占新增目录/文件：

- `scripts/generate_training_center.py`。
- `apps/api/src/corpusflow/modules/training_center/`。
- `apps/api/src/corpusflow/api/v1/training_center.py`。
- `tests/unit/training_center/`、`tests/contract/test_training_center.py`。
- 生成文件写入 `.local/training-center/<workspace-id>/<revision>/`；不提交批量生成数据和本机凭据。

工作：

1. 固定随机种子生成 CPT 2,000 篇、SFT 1,500 条、DPO 800 对，输出 manifest 与 JSONL。
2. 按来源组切分，目标分别为 1800/100/100、1350/75/75、720/40/40。生成阶段安排组大小满足目标，禁止为了凑数拆散同一来源组；不满足时明确报错。
3. 来源只使用通用类别；保留 generator、seed、schema_version、revision、文件哈希、split 与来源映射。
4. 统计来源、比例、分布、趋势和数量均从对应文件读取计算；按 revision 缓存，文件变化后刷新；页面不维护另一套总数。
5. 文件缺失、损坏、空目录有明确结果；不能静默切换为硬编码成功响应。
6. 实现契约中的目录/概览/文件/训练数据集/样本/manifest/导出只读接口，复用现有工作空间授权；实现 generated 文件适配器与 workspace 数据库适配器，后者复用已有业务查询，不改写原有构建逻辑。
7. 生成目录与真实业务数据目录使用 `catalog` 明确分开；页面不展示“模拟”角标，但 manifest 保留 provenance；不将生成来源冒充真实上传执行记录。
8. 导出调用 C 的通用序列化器，B 负责选择记录、过滤、版本和 manifest。C 未完成时可用契约样例先联调。
9. 与 C 联调后，让需要展示算子链的生成源文件实际通过处理器，记录真实运行结果；未执行的链不标记完成。

验收：相同 seed/config 生成相同内容及哈希（时间元数据不参与内容确定性）；所有引用可解析；比例合计正确；跨集合来源组不相交；更改文件后统计更新；无法读取其他工作空间目录；同 revision 下列表总数与分布总数一致。

### C：解析、清洗与导出后端

独占文件/目录：

- `apps/api/src/corpusflow/adapters/parser/`。
- `apps/api/src/corpusflow/adapters/processing/`。
- `apps/api/src/corpusflow/services/processing_pipeline.py`。
- `apps/api/src/corpusflow/worker/tasks.py`。
- 新增 `services/processing_exports.py`、`api/v1/processing_insights.py`。
- 如需要持久化扩展：`db/models.py` 和 Alembic revisions 由 C 唯一编写，A 审查；D 不另建并行迁移。
- `tests/unit/test_training_processing.py`、`tests/integration/test_training_processing.py` 及其专用 fixtures。

工作：

1. 实现文本、JSONL、CSV、DOCX 解析器，复用 `ParserAdapter/ParseResult`；MD/TXT 走文本，JSON 提供明确解析分支，不能漏掉 JSON 支持。
2. 保留 PDF/HTML 及现有 OCR/layout 入口；扫描 PDF 明确需要 OCR，DOCX 初期定义支持正文、标题与表格。
3. 未知格式先判断二进制、再尝试文本解码；编码异常、超限、结构错误返回友好错误。
4. 实现字符统一、隐私脱敏、低质内容过滤三个独立算子，复用 ProcessingAdapter/ProcessingResult。
5. 每次执行保存 operator version、config_hash、run/node ID、输入输出引用、计数、状态；不是只保存一个算子名称。
6. 与 D 在 M0 约定算子血缘所需记录；补齐原始片段到派生片段的映射，不能仅连接整份文档而丢失具体样本来源。
7. 提供处理摘要与清洗前后对比接口，F 根据真实状态展示排队/运行/失败/成功；隐私脱敏前的原文按现有权限保护。
8. 实现 JSONL/Markdown/CSV/TXT 通用序列化器与处理结果下载；CSV 多行/引号正确转义，SFT/DPO 复杂结构按契约保存。
9. 为 B 提供函数接口 `serialize_records(records, record_kind, export_format)`，输出字节块迭代器及 content_type/extension 元数据；B 不修改序列化器。

验收：8 类格式都有最小可处理样本；损坏/二进制输入有可理解错误；不增加或丢失记录的算子满足计数守恒；前后示例来自相同 record ID；失败/重试不会伪造完成状态；4 格式导出可重新读取并核对内容。

### D：血缘全栈

独占新增文件/目录：

- `apps/api/src/corpusflow/modules/lineage_graph/`。
- `apps/api/src/corpusflow/api/v1/lineage_graph.py`。
- `apps/web/src/features/lineage/`，模块客户端也放在此目录。
- `tests/unit/test_lineage_graph.py`、`tests/contract/test_lineage_graph.py`、专用血缘集成测试。

工作：

1. 实现多跳图查询、上游/下游方向、节点数与深度限制；对环路、重复节点、断链、跨工作空间引用做明确处理。
2. 在已有单跳 `/lineage/{object_type}/{object_id}` 之外新增接口，不破坏旧响应。
3. 使用 C 保存的算子执行记录展开算子节点；生成目录的来源记录由 B 的存储适配器提供。未执行的算子不生成“已执行”节点。
4. React Flow 自定义来源/文件/算子/片段/样本/数据集节点，dagre 从左到右布局；算子有序连接。
5. 所有边关系名中文化，未知关系给通用中文兜底；节点抽屉解释“这是什么、来自哪里、做了什么、流向哪里”。
6. 支持选中对象直达、缩放、拖拽、fitView；截断图明确显示尚有更多节点，不能暗示已经完整。

验收：单份文档可追溯到实际算子与数据集；图中不存在前端编造的边；相同实体节点去重；限制参数生效；节点详情和返回原页链接正确；无数据、权限失败与大图状态可用。

### E：首页与数据台前端

独占新增目录：`apps/web/src/features/training-home/`、`apps/web/src/features/data-explorer/`。

工作：

1. 首页四项关键指标、8 类格式卡片、三类数据集卡片、数据流转与活动列表。
2. 格式卡片进入对应 URL；数据台含指标、处理流转、30 天趋势、长度/语言/来源分布、文件表格、对比弹窗、关联数据集。
3. ECharts 实现统计图；各层单位不同的数据流转不使用暗示同单位流失的漏斗百分比。
4. 使用 B 的接口和共享 Query key；筛选与分页存 URL；不把当前页 20 行拿来计算全量分布。
5. 统计字段为 null 时显示“暂无统计”，不补随机增长、Tokens 或通过率。
6. 调用 C 的真实对比接口或 B 的生成目录对比接口，由 catalog 路由选择；共享对比展示组件由 E 在模块内导出，F 经约定复用。

验收：所有卡片可正确跳转；切换格式后指标/列表/分布同范围；加载/空/错状态齐全；筛选刷新不丢失；390px 与 1440px 可用；视觉接近原型。

### F：接入与清洗前端

独占新增目录：`apps/web/src/features/ingestion/`。

工作：

1. 复用现有上传、完成上传、ingest-batches 和 pipeline-runs 接口；不另造上传协议。
2. 文件格式检查、拖拽、多文件状态、解析器选择与算子配置。
3. 按真实运行记录显示横向流程，输入/保留/修改/过滤/失败分开呈现；解析阶段使用文件/片段不同单位。
4. 正确处理排队、处理中、部分成功、失败与重试；完成后调用导出，不在选择文件后直接显示成功。
5. JSONL 默认、Markdown/CSV/TXT 可选；导出范围明确是当前处理批次，显示下载错误。
6. 完成后跳转数据台、关联资产或血缘时携带 catalog=workspace 与实际 ID。

验收：真实小文件从上传到清洗和下载完整通过；刷新后可通过 runId 恢复状态；前后记录一一对应；失败步骤不显示绿色完成；格式与下载扩展名一致。

### G：三类训练数据集前端

独占新增目录：`apps/web/src/features/training-datasets/`。
可修改已有文件：`apps/web/src/pages/DatasetPage.tsx`、`DpoPage.tsx`，仅用于可选初始产品类型、嵌入构建标签页等兼容适配，保持旧用法有效。

工作：

1. CPT/SFT/DPO 复用一套概览、来源去向、分布、分页与版本选择外壳。
2. CPT 正文、SFT 多轮 messages 气泡、DPO prompt/chosen/rejected 并排渲染；保留换行，不将三类内容都强行拼成一段字符串。
3. 显示实际统计、切分、来源引用和样本状态；来源去向点击可进入 D 的血缘页。
4. 构建新版本标签复用现有 DatasetPage/DpoPage 的权限与流程。界面 CPT 对应现有 `product_type=pretrain`，不新增不兼容的 `cpt` 数据库产品类型。
5. 只读生成目录不直接调用真实发布接口；切换到“构建新版本”时明确选择真实工作空间的输入数据，不能自动把生成目录记录 ID 传入旧构建接口。
6. 四种格式导出遵循 B 的样本过滤与版本范围；选择已发布版本时仍走原有发布校验和下载权限。

验收：三个类型各能浏览与分页；切分数量与总量一致；DPO 成对保持完整；深链接恢复 dataset/version/sample；现有构建、审核、发布与下载回归通过。

### H：测试与验收

独占新增目录：`apps/web/tests/training-center/`、`scripts/verify_training_center.py`、`docs/reports/TRAINING_CENTER_ACCEPTANCE.md`。

工作：

1. 建立需求到验收映射；检查 B/C/D 的响应与共享 DTO/契约一致，开发样例不能成为唯一正确性来源。
2. 准备独立工作空间和生成目录，不清理已有开发数据；测试只删除自己创建的临时资源。
3. 三条联调线分别运行，再执行跨页面一致性、旧流程回归、权限与工作空间隔离检查。
4. 记录正式后端、开发样例与静态原型各自覆盖范围；使用开发请求拦截通过的测试不算真实 API 验收。
5. 截图回归覆盖首页、PDF 数据台、SFT 对话、DPO 对比、接入流程、血缘及移动端。

验收：报告有执行命令、环境、通过/失败/未运行、数据版本与截图；生成目录缺失、API 不可用、处理失败都真实显示；没有依赖前端伪造成功状态的用例。

## 4. 合作规则：避免互相覆盖

1. 一个负责人、一个独立分支、一个独立工作目录。示例：`feat/tc-shell`、`feat/tc-catalog-api`、`feat/tc-processing`、`feat/tc-lineage`、`feat/tc-explorer-ui`、`feat/tc-ingestion-ui`、`feat/tc-datasets-ui`、`test/tc-acceptance`。
2. 分支从同一个已提交的 M0 基线创建；原型若作为共享基准，应先提交到团队可访问分支。当前文档不会自动提交或推送这些文件。
3. A 唯一修改应用入口、全局主题、公共契约、主路由注册与锁文件；C 唯一修改数据库迁移和执行器；G 唯一适配原构建页。其它人提交变更需求，不在自己的分支顺手修改共享文件。
4. 每个功能目录自带 `api.ts`、`queries.ts`、`components/`、CSS Module，复用共享 request/下载客户端。不要继续向现有巨大的 `types.ts`、`client.ts`、`business.py` 追加所有模块代码。
5. 契约变动必须说明受影响字段和调用方。可兼容新增字段由 A 更新后通知消费者；破坏性变更先同步 B～G、更新契约版本和样例，再合并实现。
6. PR 控制在一个可验收目标，例如“JSONL/CSV 解析器”或“数据台文件筛选”，不等整个模块完成才交付。
7. A 每日集成已通过检查的 PR；H 对每条联调线提供结果。集成冲突由文件负责人解决，不通过整份文件覆盖处理。
8. 同一台机器使用不同端口/工作空间；多个后端需要隔离 Compose 项目、数据卷和队列。不要在共享后端上同时迁移、重启 Worker 或运行数据清理。
9. 各模块提供 `交付内容、文件范围、依赖版本、验证命令、已知问题、下一位接手人`。没有运行的检查写“未运行”，不能写“通过”。

## 5. 最小验证范围

- 前端模块：`npm --prefix apps/web run typecheck`、`npm --prefix apps/web run lint`、`npm --prefix apps/web run build`，以及 H 指定的本模块 Playwright 场景。
- 后端模块：对应单元/契约测试，ruff、格式、mypy；修改数据库/执行记录时增加真实隔离数据库集成检查。
- A/H 集成阶段：项目规定的完整检查、迁移至 head、`/ready`、Worker 响应、三条真实业务联调线与旧功能关键回归。
- 外部模型、付费生成或不相关历史 fixture 缺失不能用伪造结果补齐；与本次功能无关的未运行项在报告中说明。

## 6. 人数减少时如何合并职责

| 团队规模 | 建议分配 |
|---|---|
| 8 人 | A～H 各 1 人，7 开发＋1 测试 |
| 6 人 | A；B；C；D；E+G；F+H。测试职责由 F 协调，每名作者仍负责模块测试 |
| 4 人 | A+E；B+G；C+F；D+H，按完整业务线交付 |
| 3 人 | A+E+G；B+C；D+F，测试由三人互审轮值，减少同时在制任务 |

人数少时不改变接口契约与文件归属规则，只将多个角色交给同一人。

## 7. 排期参考与完成定义

以 7 名熟悉 React/FastAPI 的开发者＋1 名测试、无额外需求变更为前提，可先预留：M0 半天～1 天、M1 4～6 天、M2 2～3 天、M3 1～2 天。总计约 8～12 个工作日是排期参考，不是交付承诺；在 M0 核实数据来源关联、既有 Worker 记录和构建适配后重新估算。C 的执行记录与 D 的血缘联调是主要关键路径。

共同完成定义：

- 所有新页面能通过 hash 链接直达，登录和工作空间授权保持有效。
- 固定种子生成、manifest、只读目录、统计缓存与来源关联完整。
- 实际文件可经过解析/清洗/导出；数量、示例、状态来自真实记录。
- 首页/格式台/训练数据集在同 scope/revision 下统计一致，不能相加不同单位制造保留率。
- 血缘可追溯实际步骤；CPT/SFT/DPO 的样本结构与导出可用。
- 原构建/审核/发布流程保留；生成目录不会自动混入真实构建。
- README 与验收口径更新，准确说明可复现生成数据与真实处理的边界；不在界面加“模拟”角标，manifest 保留来源事实。
- 没有未解决的阻断缺陷，测试报告完整；仅完成静态页面不算交付完成。
