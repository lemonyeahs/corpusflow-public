# CorpusFlow 开发环境演示

先运行真实 Docker 栈，再从 apps/web 执行 npm run dev。开发身份仅用于本地演示，不能作为生产 SSO。不得演示不具备许可的真实论文。

1. 执行 `cd apps/web && npm run e2e`，准备独立测试工作空间及真实业务记录。
2. 回到根目录执行 `.venv/bin/python scripts/prepare_demo_manifest.py`，导出三组原件哈希、Run、NodeRun 和文档版本。
3. 按 DEMO_SCRIPT.md 操作；记录错误和未评估维度，不跳过失败案例。
4. 重置时重新运行 E2E，创建新工作空间。不要删库、删桶或覆盖旧发布文件。

本机 `.local/p1d/web.json` 是测试会话，禁止提交或对外分发。演示给他人时应在登录页使用新开发身份，并明确告知这不是正式身份认证。


P2 模型服务启动见 tools/semantic/README.md 和根 README。下游验证页面选择实际语义索引，比较 BM25、向量与混合，打开语义重排并查看独立分数；展示低证据/无答案误命中，不将相似度当成正确率。

已有回答展示：从本机 `.local/p2/generation-evidence.json` 读取 generation_id，使用该 fixture 工作空间登录，在「回答任务 ID」中查看；不要为了演示重复点击生成按钮。点击「查看回答证据与评分」可查看原文并录入评分。当前已用 2/10 调用，单次上限 512 输出 Token；完整生成脚本只对固定自制 fixture 幂等，不能用于外部资料。

「采集管理」只展示候选/计划/不同身份审核与本机安全拒绝；当前 DNS 不满足公网地址要求。OCR 使用 tests/fixtures/p2/raster.pdf，选择 OCR 解析器查看真实文字、页码和坐标。复杂公式表格不演示为已验证。
