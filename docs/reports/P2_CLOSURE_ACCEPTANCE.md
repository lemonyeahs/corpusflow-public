# CorpusFlow P2-Closure 最终交付验收

日期：2026-10-25；起点 `99533a5`；数据库由 `0017_generation_guards` 升至 `0018_blind_review`。

**已实现范围的开发/演示验收：CONDITIONAL PASS。完整 P2 门禁：FAIL，仍有未完成项。生产部署：FAIL。** 本轮解决了可确认的实现缺陷并保留真实失败；没有调整公网采集、专业解析或专家参与的验收标准。仅本地提交，不 push，不进入下一阶段。

## 能力矩阵

| 能力 | 当前状态 | 依据及边界 |
|---|---|---|
| 上传→解析→清洗→质量→四类产品→发布→血缘 | REAL / 回归 PASS | 真实 Docker API、Worker、PostgreSQL、MinIO 与 Web；既有开发认证限制不变 |
| 采集审核/授权隔离、安全传输与实际入库 | REAL / 有限 PASS | 自建 HTTPS 87 字节→实际 MinIO/Asset；1 Asset、0 自动用途授权；精确域名和 IP 门控 |
| 合法公网成功采集 | BLOCKED | 三域名在主机/容器均返回 198.18.x.x；连接前安全拒绝 |
| 多栏顺序/基础表格行提取 | REAL / 有限 PASS | 新 layout Adapter、真实 PDF、28 次对比；15/15 阅读顺序对、3/3 参考表格行 |
| 合并表格拓扑、数学二维语义、复杂中文 OCR | 未完成 / NOT_EVALUATED | 不能用词项、字段存在率或清晰英文扫描件替代 |
| 外部 docreader 比较 | REAL 组件实验 | 实际 gRPC builtin；扫描页仅图片引用；未交付主平台适配/外部组件部署 |
| 语义检索、重排、证据回答、质量反馈重工 | REAL / 既有范围回归 PASS | 本地真实模型、保存回答和真实 API；本轮不增加模型效果结论 |
| 分配/盲评/版本锁定/多人统计/导出 | REAL / 小规模工作流 PASS | 2 案例×2 测试员；不可覆盖、当前用途复检、真实 Web 导出 |
| 真实专家参与 | NOT RUN | 未取得真实专家身份/独立标注；只能声明系统已准备好 |
| Worker 执行中强杀恢复 | REAL / PASS | 独立数据库/队列/容器，SQL 写入时强杀，0 行回滚→26 行自动恢复 |
| PostgreSQL 与对象恢复 | REAL / 有限 PASS | 随机库 pg_dump/restore、16 个触发器；1 个原创 PDF 恢复到新 MinIO key，SHA 相同 |
| 完整公网→复杂文档→模型→专家链路 | BLOCKED / NOT RUN | 独立链路测试不能替代这条完整成功路径 |
| OIDC、生产安全、全量灾备、HA/负载 | 未完成 / NOT RUN | 开发身份不是生产认证，未访问生产环境 |

## 关键改动

1. SafeFetcher：总时间预算、慢响应中断、Content-Length/短读校验；修复完整关闭响应被误报；补齐 IPv6 转换地址和 Azure 特殊平台地址阻断。连接固定验证数字 IP、校验 peer/TLS、无环境代理、无重定向；未增加安全绕过配置。
2. LayoutParserAdapter：实际 Poppler bbox XML→双栏顺序、标题、表格行、页码/坐标；Worker `parser=layout` 进入既有持久化与幂等链路。Web 展示真实 parser_name/version。旧 parser、OCR、旧文档与原型保留。
3. Blind review Service/API/Web：任务与分配不可变、独立 evaluation 用途、角色隔离、盲评字段收敛、本人分数回显、冲突/重复提交保护、原始标注导出及 κ。禁止普通评分请求占用盲评保留键，评分回显也不泄漏回答标识。修复窄屏内容溢出。
4. 增加 4 份原创 CC0 几何版面 PDF、参考/哈希、实际输出、真实 TLS/数据库/对象测试、布局和盲评 E2E、对象恢复脚本。

主要代码：`adapters/acquisition.py`、`adapters/parser/layout.py`、`services/blind_review.py`、`services/retrieval_review.py`、`api/v1/blind_review.py`、`worker/tasks.py`、`db/models.py`；Web `BlindReviewPage`、`ProcessingPage`、`AssetsPage` 与统一 API Client。完整文件清单见 `P2_CLOSURE_CHANGESET.txt`，审阅本轮本地提交即可查看准确 diff。

## 数据库与 API

`0018_blind_review` 新增 `review_tasks`、`review_assignments`，包含 workspace/request key 唯一约束、任务/评测员唯一约束、索引与 FK；复用 `cf_quality_immutable()` 禁止 UPDATE/DELETE。评分保存在已有 `retrieval_reviews`。不变更既有 DatasetVersion/发布对象。

六个新增 HTTP 操作：POST/GET `/api/v1/review-tasks`，GET `/assignments`，GET `/assignments/{id}`，POST `/assignments/{id}/scores`，GET `/{id}/export`。统一错误 DTO；权限、当前用途和工作空间由后端决定。`RESERVED_REVIEW_KEY`、`EVALUATION_GRANT_MISSING` 等失败不变成假成功。契约为 `docs/api/openapi.json`。

## 实际测试

本机 macOS ARM64、Python 3.12；Docker PostgreSQL/Redis/MinIO/API/Worker/Dispatcher、独立本地 Embedding、Chromium。测试结束后服务保持运行。所有计数为本轮实际执行；没有把 MockAdapter 结果作为真实解析或采集证据。

| 命令/测试 | 结果 | 可查证据 |
|---|---|---|
| `EMBEDDING_ENDPOINT=http://127.0.0.1:58110 .venv/bin/python scripts/verify_p1d_environment.py` | **109 passed，0 skipped，13.35 s** | `closure_logs/pytest-final.log`；含 11 个 integration，其余 98 为单元/契约等 |
| `.venv/bin/ruff check .`、`ruff format --check .` | PASS，130 Python 文件格式通过 | 本机 final-check.log |
| `.venv/bin/mypy` | PASS，51 源文件 | 本机 final-check.log |
| `.venv/bin/python scripts/export_openapi.py` + `pytest tests/contract -q` | PASS，1 passed | OpenAPI 导出与实际应用一致 |
| `.venv/bin/alembic current` / `check` | head=0018；No new upgrade operations detected | `closure_logs/alembic.log`；全量 pytest 实际随机库升级/降级/重升级 |
| Web typecheck / lint / build | PASS，1952 模块，JS 304.97 kB | 本机 frontend-final.log |
| `npm --prefix apps/web run e2e` | **13 passed，0 skipped，75.42 s** | `closure_logs/playwright-final.log`、runtime evidence |
| 新增页面截图/断言补充复验 | **2 passed，5.8 s** | `closure_logs/playwright-visual.log`；无新增模型调用 |
| Docker `build --no-cache` | PASS，5 个应用/MinIO 镜像全新构建 | `.local/closure/docker-build.log` 哈希与尾部收录 runtime evidence |
| 最终源码 `up -d --build --wait api worker dispatcher` | PASS | deploy-final.log；完成后才跑全量回归 |
| `benchmark_closure_documents.py` | 28 次实际执行，保留失败 | parser evidence + 28 份原始输出；不是 28 次成功 |
| `verify_p2_worker_crash.py` | PASS | Worker recovery：SQL INSERT 中断，自动恢复，无共享 Worker 强杀 |
| `verify_local_restore.py` | PASS | 153568 字节 PostgreSQL 备份、0018、16 触发器/fixture 恢复 |
| `verify_closure_object_restore.py` | PASS | 原件→本地备份→新对象，原件未改写、字节 SHA 一致 |
| 公网采集 | **BLOCKED** | 3 次请求 ACQUISITION_ADDRESS_REJECTED |
| 真实专家评测、全领域复杂文档、远程 CI/生产故障 | **NOT RUN** | 没有参与者/代表资料/生产授权，未伪装通过 |

测试证据总览为 `P2_CLOSURE_RUNTIME_EVIDENCE.json`。授权回归含用途独立、撤权、跨空间、角色、自审自发、快照变更、重复消息/发布及不变版本；不是仅检查隐藏按钮。Web P0/P1 全套仍连接真实 API；109 项 pytest 中部分单元测试使用 SQLite/注入依赖，不能把其数量解释成 109 条完整端到端链路。

初次问题记录：受控 TLS 发现 Connection: close 读取错误，已修复并真实重测；盲评 fixture 使用内部 ID 调用既有接受开发 subject 的成员 API，修正测试参数；新页面窄屏溢出和提交后分数空白已修复。一次全套 Web 为 12 passed/1 failed：测试刷新到窄屏后未打开菜单，修正真实点击步骤后 13 passed。Ruff 行长、Mypy XML/dict 变量推断问题修复后静态检查通过。原始失败日志留在 `.local/closure/`，没有删除失败断言、降级测试或改为 Mock。

2362 条现存弃用警告主要为 datetime.utcnow 和 Starlette/httpx 测试客户端，未隐藏。运行时间是本机单轮测量，不提供负载 SLA。

## 模型额度与成本

本轮 **0 新付费调用**。PostgreSQL 调用预留仍为 **2/10**；每次请求最多 512 输出 Token。旧两次响应共输入 672、输出 74、合计 746 Token；本轮只读复用用于评分。供应商货币价格/账单未知，累计金额 **NOT_MEASURED**，不能写成模型免费或总体成本为零。docreader builtin 与本地 OCR/Embedding 未调用外部生成。未增加授权额度。

## 未完成、技术债与上线门禁

- 高：正常公网 DNS/出口与许可明确资源尚未获得成功证据。继续拒绝保留地址，不通过关闭 SSRF 或代理绕过实现 PASS。
- 高：复杂专业 PDF 仍缺真实领域文档、独立参考、数学二维结构、合并格拓扑及中文复杂 OCR 可靠性。新布局只是在指定 fixture 上改善；外部 docreader 仅比较，未正式接入主平台。
- 高：真实专家未参与；开发身份、专家资质核验、严格平台级双盲、仲裁/无法判断流和大规模标注尚不完整。
- 生产阻断：OIDC/SSO、网络 egress/密钥治理、全量数据库+对象一致性灾备、RPO/RTO、HA、压力测试、依赖 SBOM/漏洞治理。单库 schema/fixture 和单对象恢复不能替代完整灾备。
- 中：采集孤儿对象自动 GC；任务列表 200 条上限；格式警告与依赖升级；精确向量 5000 Chunk 和模型截断限制；bi-encoder 重排未证明专业效果提升。

## 回滚与交付保护

优先停用 layout/盲评新增入口及新任务，保留数据库、历史文件与评分；不要自动 downgrade。0018 降级将删除任务/分配，应停写并导出原始评分和冻结报告、备份确认后才评估。测试中的 downgrade 仅用于脚本创建的随机库；未对业务库降级。所有恢复/故障对象有独立标识，没有删共享卷或用户数据。

原型 HTML 与 CHANGELOG 与 `99533a5` 的字节完全一致，SHA 记录在 runtime evidence。没有覆盖历史发布、重建业务数据库、访问生产或远程 push。`.env`、会话、模型凭证、备份与大日志保持忽略；小型原创 PDF、脱敏证据和实际截图纳入交付。本轮本地提交 ID 由最终交付消息和 Git log 给出，报告本身随该提交保存。

操作见 `docs/demo/FINAL_DEMO_GUIDE.md`；专家标准见 `EXPERT_EVALUATION_GUIDE.md`。完成本轮收敛后停止。
