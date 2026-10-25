# 演示脚本

1. 登录独立开发工作空间，创建来源，选取普通 PDF；展示选中文件还没有 Asset。
2. 上传登记后查看 SHA-256；创建包含 clean/deduplicate/quality 的处理任务。
3. 等待 Worker succeeded，查看 NodeRun、清洗前后产物与 Segment 原文位置。202 仅表示受理。
4. 打开质量中心，展示规则版本和 NOT_EVALUATED 项；用损坏 PDF 展示明确错误与驳回门控。
5. 为原创数据登记可核对的用途许可，选择 RAG 或 Evaluation 产品；审核候选后由另一身份发布。
6. 下载真实 JSONL、Manifest，核对哈希并追踪原文件。用途不足或自审自发应被拒绝。
7. 下游验证创建索引，依次查询 AES block size、Merkle root、AES inventor favorite coffee。
8. 对比固定评测集的 FTS/BM25/RRF 结果；最后一个问题可能有词法命中，但没有支持答案，不展示生成成功。
9. 提交质量反馈，由 reviewer 复核，显式恢复；观察新文档版本和新索引。旧版本不变。

模型生成、向量平台集成、复杂 OCR 或正式 OIDC 未通过验收时必须展示为未接入，不能口头宣布已实现。
