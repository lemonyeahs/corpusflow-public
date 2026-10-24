# P1-C 数据集版本比较样例

比较结果来自真实发布的两个 Pretrain DatasetVersion，未修改任一版本或其对象。比较服务按稳定 `sample_key`、来源、内容哈希和 payload 哈希联合识别样本。

## 真实结果

最近一次比较记录在 `.local/p1c/evidence.json` 的 `comparison` 字段：

| 项目 | 结果 |
|---|---:|
| 新增样本 | 0 |
| 删除样本 | 0 |
| 保留样本 | 1 |
| 内容变化 | 0 |
| Token 数变化 | 0 |
| 样本数变化 | 0 |
| 质量指标可比性 | `COMPARABLE` |
| 规则版本 | 两侧相同 |
| tokenizer | `builtin-whitespace-1`，两侧相同 |

比较仍记录了 Manifest 内容 SHA-256、对象路径、构建配置、质量快照、来源/领域/划分分布和报告 ID。即使稳定样本标识相同，Manifest 或 payload 变化也会在 `manifest_diff` 或 `changed` 中体现。

## 不可直接比较条件

当规则版本、规则配置哈希或 tokenizer 版本不一致时，比较结果保留样本级差异，但 `quality_comparison` 返回 `NOT_COMPARABLE` 并给出原因；系统不会把不同口径的指标直接相减。需要统一口径时，应新建独立评估记录后再比较。
