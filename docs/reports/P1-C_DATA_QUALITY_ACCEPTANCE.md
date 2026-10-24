# CorpusFlow P1-C 数据质量治理验收

## 结论

**CONDITIONAL PASS（开发/演示环境）**。质量规则、真实评估、覆盖/配比、版本比较、不可变快照、发布门控和 Web 展示已实现并通过本地验证。正式生产身份、目标领域全集、人工公式/表格/OCR 标注及语义级重复检测仍未接入，因此不能宣称生产级领域覆盖或专业质量准确率。

## 实现与变更

- 新增 `QualityRuleSet`、`QualityRuleVersion`、`QualityEvaluationRun`、`QualityMetricResult`、`DatasetQualityReport`、`DatasetVersionComparison`。
- 新增迁移 `0009_p1c_quality_governance` 和 `0010_p1c_quality_guards`，当前 head 为 `0010_p1c_quality_guards`；完成评估、质量报告、比较快照的数据库不可变触发器和索引。
- 新增确定性质量服务：规则快照、指标分子/分母/单位/阈值/方向/evidence、授权硬门控、source quality、evaluation leakage、覆盖、配比和版本差异。
- 发布 API 在物化前重新评估 build；质量或授权 gate 失败返回 `QUALITY_GATE_FAILED`，并把通过的报告快照写入不可变 Manifest/`DatasetQualityReport`。
- 新增 API：`GET /quality/rules`、`POST /quality/rules/versions`、`POST/GET /quality/evaluations`、`GET /quality/evaluations/{id}`、`GET /quality/reports/{dataset_version_id}`、`GET /quality/coverage`、`GET /quality/ratios/{dataset_version_id}`、`POST/GET /quality/version-comparisons`。
- Web 质量中心支持规则版本、评估、指标状态、覆盖、配比、版本比较和 JSON 导出；正式数据全部来自 API。
- 修复显式质量重工复用已发布 Outbox 事件的问题，允许新 attempt 重新投递且保持 worker 按业务 ID 幂等。

## 真实证据

`scripts/verify_p1c_quality.py` 使用隔离本地 PostgreSQL、Redis、MinIO 和真实 Worker，完成 11 项检查：四类产品各一份 JSONL 发布及 SHA-256 校验、不可变质量快照、版本比较、规则版本重评估、失败质量阻断、撤销授权阻断、数据库不可变触发器、跨 workspace 拒绝、多标签去重覆盖。证据写入 `.local/p1c/evidence.json`，不会纳入 Git。

## 测试结果

| 检查 | 结果 | 实际输出 |
|---|---|---|
| 单元/契约回归 | PASS | `46 passed, 4 skipped`；4 个集成用例因未设置隔离对象存储/数据库环境变量而跳过 |
| 质量真实业务脚本 | PASS | `P1-C QUALITY PASS: 11 real checks` |
| P0-B～F 业务脚本 | PASS | P0-C、P0-D、P0-E、P0-F PASS |
| Alembic 迁移升级/降级/重升 | PASS | `1 passed` |
| OpenAPI 契约 | PASS | `1 passed` |
| Ruff | PASS | `All checks passed!` |
| Mypy | PASS | `Success: no issues found in 35 source files` |
| Web typecheck/lint/build | PASS | Vite build 成功，278.91 kB JS |
| Playwright 真实 API E2E | PASS | `6 passed`（P0-H、P0-I、P1-A、P1-B、P1-C、窄屏） |
| Docker compose 镜像重建 | NOT RUN/环境失败 | PyPI `hatchling` 下载超时；现有本地 Docker 运行栈健康，E2E 使用真实服务完成 |

异常路径已验证：撤销授权不能推导训练授权；元数据阈值提高产生新的失败评估；失败评估阻断发布；跨 workspace 的报告、评估、比较、配比和过滤覆盖查询被拒绝；已完成质量 run/report 不能通过数据库更新；历史 DatasetVersion 保持不变。

## 未完成与风险

- 尚未接入 OIDC/正式生产身份认证，当前 token 身份仅适用于隔离开发环境。
- 没有可信目标领域全集，所以覆盖率只能表示已登记资源分布；`domain.knowledge_coverage` 为 `NOT_EVALUATED`。
- 公式、表格、OCR 和领域相关性没有人工参考标注，对应指标为 `NOT_EVALUATED`；当前异常字符/HTML 噪声是可解释启发式指标。
- 仍未实现语义向量级重复检测、自动目标配比优化和 CSV 导出。
- 当前仅验证本地 MinIO；生产对象存储、密钥轮换和跨区域交付不在本阶段。
- Docker 镜像重建受外网 PyPI 超时影响，需要网络可用后重新执行 `docker compose build`。

## 本地复现

```bash
docker compose --env-file .env -f infra/compose.yaml up -d --wait
make openapi
.venv/bin/pytest -m 'not integration' -q
.venv/bin/python scripts/verify_p1c_quality.py
cd apps/web && npm run e2e -- --project=chromium
```

不执行远程 push，不访问生产环境，不覆盖 V3.1 原型或历史发布对象。P1-D 的在线 RAG、向量检索和模型效果评测不在本轮范围内。
