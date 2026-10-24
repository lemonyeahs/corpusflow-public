# P0-C Ingestion 验收

日期：2026-10-24（Asia/Shanghai）  
任务：TASK-CF-003。范围：FR-002/003/011～016、AC-ING、AC-ASSET、TC-01～04/10。

## 实现

- `upload_sessions`、`asset_blobs`、`sources`、`ingest_batches`、`ingest_batch_items`、`assets` 与 discovery candidate 表及迁移。
- `uploads/init → uploads/{id}/content → complete → ingest-batches`；服务端计算 SHA-256，仅 verified 上传登记 Asset。
- 每个文件独立状态；重复字节返回 duplicate；候选 URL 只创建 Candidate，不增加 Asset；资产查询和统计限定 workspace。

## 实测

- `scripts/verify_business_loop.py` 中真实 API 流程：3 文件中第 1 个未完成上传，第 2/3 成功，返回 `total=3,succeeded=2,failed=1`；后续三份真实字节分别登记为 Asset。
- 可重复脚本输出：[P0_BUSINESS_LOOP.log](P0_BUSINESS_LOOP.log)。
- 迁移 `upgrade head → check → downgrade base → upgrade head`：`1 passed`，最终 revision `0002_business、0003_immutable_release`。
- 运行期间未修改 V3.1 原型或生产环境。

## 结论与边界

P0-C 门禁通过，可进入 P0-D。病毒扫描、URL/DOI 真实采集、S3 multipart 预签名和大文件分片仍是后续增强项；当前上传字节在持久化登记流程中保存并校验，不能宣称已完成外部采集。
