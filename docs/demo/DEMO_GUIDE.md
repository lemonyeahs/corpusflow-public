# CorpusFlow 开发环境演示

先运行真实 Docker 栈，再从 apps/web 执行 npm run dev。开发身份仅用于本地演示，不能作为生产 SSO。不得演示不具备许可的真实论文。

1. 执行 `cd apps/web && npm run e2e`，准备独立测试工作空间及真实业务记录。
2. 回到根目录执行 `.venv/bin/python scripts/prepare_demo_manifest.py`，导出三组原件哈希、Run、NodeRun 和文档版本。
3. 按 DEMO_SCRIPT.md 操作；记录错误和未评估维度，不跳过失败案例。
4. 重置时重新运行 E2E，创建新工作空间。不要删库、删桶或覆盖旧发布文件。

本机 `.local/p1d/web.json` 是测试会话，禁止提交或对外分发。演示给他人时应在登录页使用新开发身份，并明确告知这不是正式身份认证。
