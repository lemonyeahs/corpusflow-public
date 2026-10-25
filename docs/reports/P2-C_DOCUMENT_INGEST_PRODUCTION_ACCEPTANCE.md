# P2-C 文档、采集与生产化加固

结论：PARTIAL / CONDITIONAL PASS（仅已验证的 OCR 与采集拒绝路径），完整阶段门禁未通过。公网采集成功路径被本机 Fake-IP DNS 阻断，复杂版面与正式身份尚未验收。

## 真实 OCR 平台

冻结配置 `parser=ocr`，实际从 MinIO 取原始 PDF，Docker Worker 调用锁定直接包版本 Tesseract 5.5.0-1+b1、Poppler 25.03.0-5+deb13u4、eng 1:4.1.0-2。输入 20 MiB、1–10 页、渲染长边 2400、单子进程最多 30 秒、整个 OCR 180 秒。配置、解析器、输入输出计数、耗时、词坐标、引擎置信度及 JSON/Markdown 产物进入既有 Run/NodeRun/DocumentVersion/Segment 链路。

真正图片型 `tests/fixtures/p2/raster.pdf`：内置解析器返回 SCANNED_PDF_UNSUPPORTED；OCR 实际读取「CorpusFlow OCR evidence: AES block size is 128 bits.」，重复投递不增加文档版本。Web 从真实 API 显示文本。修复原解析失败未写 NodeRun.failure_code 的诊断缺陷，并使 Run 查询返回 error_code。文档复用同时核对 parser_name、parser_version 和配置哈希，避免复用不兼容结果。

旧 P1-A scanned.pdf 是空白页；没有覆盖旧 fixture 或将其当作 OCR 成功证据。中文、复杂表格、公式结构、多栏顺序、图注准确率：NOT_EVALUATED。docreader ListEngines 实测仅证明服务可达，未完成专业文档适配。

## 受控采集

0015 新增 IngestPlan；Candidate → 冻结计划 → 不同身份审核 → Outbox → Worker → 条件写对象 → Asset/血缘。每计划最多 10，审批不自动产生任何用途授权。支持 URL 候选与 Crossref DOI 元数据接口（排除摘要和全文），计划/审核/状态 Web 页面。

SSRF：管理员精确主机白名单、HTTPS/443、禁止凭据/控制字符、所有 DNS 地址须公网、固定验证 IP 建立 TLS 并检查主机名、禁代理、拒绝全部重定向、拒绝压缩传输、15 秒和 20 MiB 上限；DNS 解析线程池有界并设等待超时。不是生产网络隔离替代品。直接 apt 包版本锁定，传递系统依赖尚未建立完整 SBOM。

实际 Crossref 请求被拒绝：宿主机和 Docker 均解析为 198.18.0.117。没有降低地址门控或声称下载成功。审核职责分离、幂等、跨空间、Worker 实际拒绝、零 Asset/零授权、驳回后不可重新批准已验证。

Crossref 元数据许可与协议参考：[官方 REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)。元数据中的 license 字段仅作声明，不是 CorpusFlow 用途授权。

## 测试与限制

- pytest 89 passed、0 skipped（本地模型显式配置）；真实迁移往返、MinIO、OCR/Embedding；`phase-c-pytest.log`。
- `make check`：82 非集成测试通过，ruff/mypy/契约通过。前端 typecheck/lint/build 通过。
- `verify_p2_ocr.py` 和 `verify_p2_collection.py` 通过实际服务。Playwright 验证 OCR 文本、采集错误、候选登记和窄屏；首次窄屏溢出已修复，复验结果见最终报告。
- 全套 P0/P1 回归和隔离故障验证最终单独记录。
- 外网成功采集、完整复杂文档指标、OIDC/SSO、多节点 HA、真实生产压力、依赖漏洞治理仍 NOT RUN / 未完成，不能宣称生产就绪。

失败事务不暴露成功 Asset；对象先写、数据库提交失败可能留下 acquisition 前缀下孤儿对象，按计划 ID 可诊断，尚无自动垃圾回收。回退停用采集/模型入口并保留数据；0015 downgrade 删除新计划表，须先备份，不自动执行。既有发布文件不变。


## 最终独立故障与备份恢复

- `scripts/verify_p2_worker_crash.py`：PASS。随机独立数据库、Redis 队列和键前缀、自建 Worker 容器；通过 PostgreSQL 活动视图确认任务正在 INSERT，强杀后数据库 0 行，重启后依靠 Redis visibility timeout 自动恢复为 26 行，无手工重新投递。共享 Worker 未被终止。证据 `P2-C_WORKER_RECOVERY_EVIDENCE.json`。此验证针对索引写入边界，不扩大解释为所有任务/LLM 故障都已覆盖。
- `scripts/verify_local_restore.py`：PASS。对自建临时库实际 pg_dump/pg_restore，146,896 字节；恢复到 0017、真实 fixture 行和 14 个用户触发器。证据 `P2-C_RESTORE_EVIDENCE.json`。生产 RPO/RTO、MinIO 备份恢复未验证。
- 迁移中补齐的 0017 保护真实生成结果与调用预留，防止重置预算造成重复费用；真实 PostgreSQL 拒绝变更测试通过。
- 最终后端 92 passed，Web 全套 11 passed（额外回答评分用例复验 1 passed），ruff/mypy/typecheck/lint/build/契约/迁移检查均 PASS。全部本地执行，远程 CI 未运行。

曾出现测试夹具并发覆盖（10 passed / 1 failed），原因是多个 spec 共用生成的会话文件；Playwright 改为单 Worker 后完整复验 11 passed。断言和真实服务未替换。第一次故障脚本使用旧镜像，参数不兼容，未达到强杀边界；重建后完成上述真实恢复，失败未计入成功。

当前不存在从公网获取原件后贯通 OCR、发布、问答的成功证据。该全链路仍 BLOCKED，不能用本地上传和 SSRF 拒绝测试替代公网采集成功。
