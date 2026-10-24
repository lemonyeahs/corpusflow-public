# P0-B IAM + Policy 验收

日期：2026-10-24（Asia/Shanghai）  
任务：TASK-CF-002。范围：FR-010/027/028/041、BR-AUTH、AC-IAM、TC-05～08/19。

## 实现

- `users`、`workspaces`、`workspace_memberships`、`license_evidence`、`license_grants`、`audit_events` 持久化表。
- `/api/v1/auth/session`、`/auth/me`、`/workspaces`、成员管理、许可授予和 `/authorization/decisions`。
- 后端按 workspace、role、purpose 和 confirmed evidence 求值；无 grant 默认拒绝，purpose 不继承；写操作生成审计事件。

## 实测

- `set -a; source .env; set +a; CF_TEST_ADMIN_DATABASE_URL=... uv run --locked pytest -q tests/integration/test_migration.py`：`1 passed`。
- 原始迁移输出：[P0-B_MIGRATION.log](P0-B_MIGRATION.log)；静态和基础测试输出：[P0_B_static.log](P0_B_static.log)。
- `uv run --locked ruff check .`、`uv run --locked mypy`、`uv run --locked pytest -q tests/unit tests/contract`：静态检查通过，`12 passed`。
- 真实 PostgreSQL API 冒烟：无 grant `training` DENY；仅 research grant 仍 DENY training；confirmed training grant ALLOW；非成员跨空间读取返回 403；审计事件可查询。

## 结论与边界

P0-B 门禁通过，可进入 P0-C。OIDC/生产身份提供商尚未接入；当前 session 是明确的开发身份交换，生产环境仍禁止把它当作 OIDC。
