# P0-B～P0-F 业务闭环总验收

日期：2026-10-24（Asia/Shanghai）。各阶段按 P0-B→P0-C→P0-D→P0-E→P0-F 顺序执行，独立门禁均通过。

| 阶段 | 报告 | 核心证据 |
|---|---|---|
| P0-B | [P0-B_ACCEPTANCE_FINAL](P0-B_ACCEPTANCE_FINAL.md) | 迁移 1 passed；默认拒绝、用途隔离、空间隔离 |
| P0-C | [P0-C_ACCEPTANCE](P0-C_ACCEPTANCE.md) | 3 文件部分失败隔离；真实字节哈希登记 |
| P0-D | [P0-D_ACCEPTANCE](P0-D_ACCEPTANCE.md) | N=3 Run；审核阻断→显式恢复→新产物 |
| P0-E | [P0-E_ACCEPTANCE](P0-E_ACCEPTANCE.md) | 候选审核、发布 gate、不可变版本 |
| P0-F | [P0-F_ACCEPTANCE](P0-F_ACCEPTANCE.md) | workspace-scoped lineage、审计、OpenAPI |

## 可复现命令

```sh
set -a; source .env; set +a
uv run --locked alembic upgrade head
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -q tests/unit tests/contract
uv run --locked python scripts/verify_business_loop.py
```

## 交付边界

本次没有 push、没有生产迁移、没有删除原有卷或覆盖 V3.1。外部 OIDC、病毒扫描/采集、Celery Outbox/租约、真实 docreader/Data-Juicer/LLM、发布对象物化、正式 Web UI E2E 和 P1 RAG 仍需后续阶段。
