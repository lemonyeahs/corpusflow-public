# DPO 数据产品需求

## 范围

DPO 产品负责把已经有训练用途授权的 Prompt、成对候选回答、证据和人工偏好标注物化为不可变 JSONL。它不执行 DPO 训练、不调用模型自动扩大预算，也不把模型生成结果视为人工偏好结论。

## 状态与门控

偏好样本状态为 pending、annotated、tie、uncertain、rejected、approved。只有存在明确 chosen/rejected、证据可追溯、训练授权有效、审核职责分离且质量评估通过的 approved 样本才可以进入 DPO 构建。

导出 Schema dpo.v1：

~~~json
{"prompt":"...","chosen":"...","rejected":"...","evidence_ids":["segment-id"],"source_id":"source-id"}
~~~

平局、无法判断、两者均不合格、回答相同、证据缺失、跨 workspace 或授权不足均阻断。

## 标注标准

标注者比较事实准确性、证据支持性、完整性、指令遵循、表达清晰度和无依据内容。系统保存每位标注者的选择、理由、标注版本和展示顺序；冲突保留为 uncertain，由不同于导入者和标注者的审核人复核。测试身份不代表密码学专家。

## 与 SFT 的区别

SFT 是单条消息序列，DPO 是同一 Prompt 下的 chosen/rejected 成对偏好。DPO 不复用 SFT 的回答 Schema，也不允许把拒答或平局静默转换成负样本。
