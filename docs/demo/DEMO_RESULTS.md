# 演示复验记录

2026-10-25：真实 Docker Web E2E 7 passed；pytest 69 passed。三组资产由 prepare_demo_manifest.py 实际查询，完整 ID、哈希、处理状态见 DEMO_EVIDENCE.json。

31 条查询与六组实验复现通过；BM25 有答案召回率 1.0，但无答案空召回率 0.75，不代表专业问答质量满分。开发 reviewer 不等于真实专家。

截图：本轮真实 Playwright 导出 `.local/demo/retrieval.png`，已目视检查；展示真实查询、评测记录和反馈。生成仍为 NOT_CONFIGURED，排队任务没有伪装为成功。该临时截图不纳入 Git。跨三个样本组的单一工作空间连续演示尚未验收；现阶段提供可复现步骤和独立真实链路，演示整体为 PARTIAL。
