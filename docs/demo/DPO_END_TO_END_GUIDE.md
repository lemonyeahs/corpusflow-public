# DPO 端到端演示指南

1. 在开发 workspace 中确认来源的 training grant、Segment 和质量状态。
2. 进入“DPO 偏好”，导入自制 Prompt、Response A/B、Source 和 Evidence Segment。
3. 使用至少两个不同的 reviewer 身份提交选择；A/B 冲突会进入 uncertain，不得审核通过。
4. 由未导入且未参与标注的审核人确认偏好，状态变为 approved。
5. 创建 DPO Dataset，选择已审核样本，调用 DpoBuilder。
6. 验证 Build 快照后，由发布管理员执行现有版本发布。
7. 查看 dpo.v1 Manifest、SHA-256、短期下载授权和 PreferenceSample → Segment → DatasetVersion 血缘。

本指南使用 fixture 时必须标记 fixture/demo。模型生成默认关闭；不存在真实模型服务或预算授权时只走导入路径。DPO DatasetVersion 只代表训练数据准备完成，不代表模型训练或效果提升。
