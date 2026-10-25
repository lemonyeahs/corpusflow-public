# CorpusFlow 最终开发环境演示指南

以 `P2_CLOSURE_ACCEPTANCE.md` 为当前结论。演示是真实开发系统，不是 V3.1 HTML；完整 P2 和生产门禁尚未通过。只使用仓库原创 CC0 fixture，不引入未知许可资料。

## 启动

已有 `.env` 和卷必须保留。新环境才运行 `make install`、`make init-env`。基础启动：

```sh
cd /Users/leon/Desktop/data
docker compose --env-file .env -f infra/compose.yaml up -d --build --wait api worker dispatcher
curl -f http://127.0.0.1:58000/ready
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

API `127.0.0.1:58000`、Web `127.0.0.1:5173`。基础配置禁用外部生成。语义服务需已有获准的本地模型目录，按 `tools/semantic/README.md` 启动；不自动下载模型。本次机器使用已存在的忽略文件 `.local/p2/compose-vector.yaml` 和 `.local/p2/compose-llm.yaml` 启动验证配置。它们不随仓库交付，不能在新机器假定存在，也不要打印或复制其中凭证。

新环境可配置本地 Embedding，但付费模型仅在授权测试空间内启用。不要为了复现演示调用生成 API；已有回答及只读证据足以展示本轮功能。新机器缺少保存回答时，答案盲评演示应标 NOT RUN，或准备有证据的 retrieval-only 任务，不伪造回答。

## 操作顺序与预期

1. **原始接入**：登录受控开发身份，上传 `tests/fixtures/closure/columns.pdf`；登记为 Asset，查看真实 SHA。没有明确用途授权时不进入训练/RAG/评测。不要把研究授权当作其他用途。
2. **解析与清洗**：处理中心选择 layout 参数执行；显示异步 Run 和节点实际状态。完成后在资产中心查看标题、左栏完整后右栏的 Segment，以及 `local.poppler-layout · 1.0.0`。通过现有处理详情查看 JSON/Markdown、定位和清洗对照。图片扫描件选择 OCR；损坏/加密文件应失败。
3. **治理与产品**：使用既有真实 fixture/许可证据，进入质量审核、四类产品独立配置、候选审核、不同身份发布。下载 JSONL，核对 Manifest 和 SHA，反向查看原件。完整回归由 `npm --prefix apps/web run e2e` 创建新测试空间；不删除旧空间或版本。
4. **检索和回答**：下游验证选择真实已发布 RAG 版本/索引，查看词法、语义、重排分数和证据。展示已保存回答与拒答；不要把相似度当作质量，不点击新增生成。保存回答属于先前 2 次实际模型请求，不是本轮新实验。
5. **盲评**：按 `EXPERT_EVALUATION_GUIDE.md` 分配冻结任务。评测员独立填写，管理员导出原始标注和分歧。当前示范分数明确标注 synthetic workflow，不说明专家参与。
6. **反馈重工**：查看实际低质量检索反馈与关联 QualityIssue，按已有流程重工，保留旧版本与血缘；不得把新版本等同效果改善。
7. **受控采集**：展示候选、不同身份审核、Worker 执行与错误诊断。当前公网 DNS 为非公网地址，必须展示 BLOCKED。另用受控 HTTPS 测试日志展示成功的实际对象字节和 Asset；明确这不是公网成功。

## 可复现验证

```sh
EMBEDDING_ENDPOINT=http://127.0.0.1:58110 .venv/bin/python scripts/verify_p1d_environment.py
.venv/bin/python scripts/verify_closure_layout.py
npm --prefix apps/web run e2e
.venv/bin/python scripts/verify_p2_worker_crash.py
.venv/bin/python scripts/verify_local_restore.py
.venv/bin/python scripts/verify_closure_object_restore.py
```

完整 Web 用例依赖已配置本地模型和既有回答 fixture；不会伪造缺失依赖。`verify_closure_reviews.py` 从本机忽略文件加载既有会话/回答，不新增生成请求。故障脚本只强杀自己创建的隔离 Worker，恢复脚本仅创建/清理自有随机数据库，不能改成业务库名。

解析对比：`.venv/bin/python scripts/benchmark_closure_documents.py`。需要本机 Poppler/Tesseract，以及实际 `WeKnora-docreader` 容器；没有外部组件时相应项为 NOT RUN。不要把 ListEngines 可达当作解析通过。

## 演示边界

不能宣称公网→专业复杂 PDF→模型→真实专家全链路通过。没有真实专家、中文复杂 OCR、公式二维结构、生产 OIDC 或完整灾备承诺。演示恢复使用新工作空间/新任务，不清库、不覆盖原型、已发布对象或历史评分。本轮停止，不进入后续研发阶段。
