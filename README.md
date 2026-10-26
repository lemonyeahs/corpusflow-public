# CorpusFlow

训练数据中心改版协作入口：[Agent 开工规则](AGENTS.md) · [两人四 Agent 协作指南](docs/plans/TRAINING_CENTER_AGENT_COLLABORATION.md) · [并行开发任务书](docs/plans/TRAINING_CENTER_PARALLEL_PLAN.md) · [接口契约草案](docs/specs/TRAINING_CENTER_CONTRACT_V1.md) · [HTML 界面原型](docs/previews/training-data-center.html)。本组资料用于规划与视觉确认，尚未代表新业务功能已实现。

当前交付包含真实 Web 数据工程工作台、P0/P1 核心闭环与已验证的 P2 增量。最新数据库迁移为 `0021_metadata_proposals`。**开发/演示环境已实现范围 CONDITIONAL PASS；完整 P2 与生产门禁尚未通过。** 本轮工作台重构验收见 [工作台重构验收](docs/reports/WORKSPACE_REFACTOR_ACCEPTANCE.md)，演示步骤见 [新工作台演示指南](docs/demo/NEW_WORKSPACE_DEMO_GUIDE.md)。V3.1 HTML 保留为独立 DEMO 参考，不代表工程实现状态。

## 本地启动

前置：Docker Engine / Docker Desktop 与 Compose、Python 3、uv、make。服务仅绑定本机回环地址。本阶段拒绝 staging/production 配置。

MinIO 从官方固定提交构建，源码、Go 依赖与基础镜像均校验锁定，详见 [镜像构建说明](infra/docker/minio/README.md)。首次构建需要足够磁盘空间及 GitHub codeload、Go module proxy/checksum、官方基础镜像注册表访问。磁盘与 Docker 恢复后，完整本地 ARM64 复验已通过，详见 [最新验收报告](docs/reports/ENV_REVERIFY_RECOVERED_ACCEPTANCE.md)；远程 CI 尚未重跑。

```sh
make init-env    # 只在 .env 不存在时创建随机本地凭证；不会打印凭证
make up          # 拉取依赖、构建 API、迁移、创建开发桶并启用版本控制
```

访问 [健康检查](http://127.0.0.1:58000/health)、[就绪检查](http://127.0.0.1:58000/ready)、[OpenAPI 文档](http://127.0.0.1:58000/docs)。`/health` 只证明进程存活；`/ready` 必须实际通过 PostgreSQL SELECT 与 Alembic 版本核对、Redis PING、S3 签名 HeadBucket 才返回 200。失败返回 503 和依赖名称，不返回连接凭证。

已有 `.env` 时保留原文件，按 `.env.example` 检查字段。凭证不应包含 URL 保留字符，或需先 URL 编码；推荐使用脚本生成的十六进制随机值。不要对已有数据卷直接更换初始化密码。

## 本机开发和检查

```sh
make install              # uv sync --locked；Python 3.12
make check                # ruff、format、mypy、单元与契约测试
make openapi              # 导出 FastAPI 契约；提交时与代码一起审阅
```

执行 `make verify-environment` 重放完整检查。脚本先确认本机 Docker 可响应和至少 15 GiB 空闲空间，再创建随机项目名、凭证、回环端口和独立测试卷，顺序无缓存构建 MinIO/API，执行迁移、S3 及探活恢复测试；停止临时项目时不删卷。报告默认写入 `.local/cf-verify-*`，使用 `VERIFY_ARGS="--report-dir <新目录>"` 可指定新报告目录，已有目录拒绝覆盖。仅允许本机 Docker socket；现有开发 `.env` 和 `corpusflow-p0a` 卷不用于复验。

容器 API 与本机开发默认使用同一端口，运行 `make dev` 前先停止 API 容器：

```sh
docker compose --env-file .env -f infra/compose.yaml stop api
make dev
```

迁移检查只允许明确指定的回环测试数据库，脚本创建随机临时库，完成后仅删除自己创建的临时库：

```sh
set -a
. ./.env
set +a
export CF_TEST_ADMIN_DATABASE_URL="$DATABASE_URL"
make integration
```

无 `CF_TEST_ADMIN_DATABASE_URL` 时集成测试显示 SKIP，不算通过。生产数据库禁止运行上述测试。初始化迁移为 `0001_p0a`，业务表在 `0002_business`、发布不可变保护在 `0003_immutable_release`、异步执行在 `0004_async_processing`、数据集物化与交付在 `0005_dataset_materialization`；均需在本地测试库执行迁移检查，不对生产自动运行。

```sh
make down                 # 停服务并保留所有 named volumes
```

回滚：停止新增功能并保留数据。当前业务迁移 downgrade 会删除表或字段，绝非只回退版本标记；仅能在独立临时测试库验证。实际部署须先完成备份恢复验证和数据导出，不提供自动清库回滚。原型原件未修改。

## 目录与边界

- `apps/api/src/corpusflow`：API、配置/错误/日志、DB、业务路由与策略、真实依赖探测；`modules/*` 保留后续扩展边界。
- `apps/api/alembic`：版本化迁移。业务 Service 持有事务边界，禁止 ORM event 复制业务策略。
- `apps/web`：React/Vite 真实业务工作台；`docs/prototype` 为原型只读参考副本。
- `infra`：PostgreSQL 16、Redis、MinIO、API、Worker 和 Outbox Dispatcher 的本地 Compose。
- `tests`：单元、契约、独立临时 PostgreSQL 迁移测试；`scripts/verify_business_loop.py` 覆盖 P0-B～F 业务门禁。
- `docs/plans`：现状、分阶段任务、追踪矩阵、待确认决策。
- `docs/reports/P0_DATASET_MATERIALIZATION_ACCEPTANCE.md`：P0-G 数据集物化、发布和交付证据。

分层：Router → Application Service → Domain Policy → Repository / Adapter。当前开发身份 session、内置 parser、Celery/Outbox 和本地数据集物化是受控本地实现；生产 OIDC 尚未接入；React Web、本地 OCR、语义模型和受控外部生成已按以下 P2 范围接入。请求 JSON 日志不能替代不可变业务审计。

项目仓库：[lemonyeahs/corpusflow](https://github.com/lemonyeahs/corpusflow)（私有）。默认分支为 `main`。P0-A 验收报告记录首次发布前的本地验收状态；远程 CI 结果以 GitHub Actions 为准。首次远程运行的镜像拉取限制见 [GitHub 上传记录](docs/reports/GITHUB_UPLOAD.md)。

当前完整流程已在本机 ARM64 验证，远程 CI 未重跑。基础镜像固定摘要，MinIO 固定源码提交及下载包校验值；AMD64 兼容与生产镜像安全评估未完成，详见验收报告。

## P0-H Web 联调

Web 工作台位于 `apps/web`，采用 TypeScript + React + Vite，通过 Vite `/api` 代理连接本地 FastAPI。启动真实后端后执行：

```bash
docker compose --env-file .env -f infra/compose.yaml up -d postgres redis minio init api worker dispatcher
cd apps/web && npm ci && npm run dev
```

静态检查和真实 Docker Playwright 测试：

```bash
npm run typecheck
npm run lint
npm run build
npm run e2e
```

P0-H 交付报告见 [`docs/reports/P0-H_WEB_ACCEPTANCE.md`](docs/reports/P0-H_WEB_ACCEPTANCE.md)。

## 数据产品与 P1-D 下游验证

数据产品中心支持 Pretrain、SFT、RAG、Evaluation 和 DPO 五类产品。DPO 页面从已授权来源导入成对候选回答，保存独立标注、冲突和审核记录，使用 `DpoBuilder` 生成 `dpo.v1` JSONL，并复用现有质量门控、MinIO 不可变发布、Manifest 和血缘。DPO 数据准备不等于 DPO 模型训练；本仓库不包含训练器。

## P1-D 真实检索与评测

“下游验证”页面现提供真实发布 RAG 索引、PostgreSQL FTS/Unicode BM25、词法混合与词项重排、固定评测和质量反馈重工。未配置模型时明确显示不可用；P2 增量配置见下文，不提供预设回答。

```bash
# 在根目录执行，已有 .env 不覆盖；先等待依赖启动，再运行测试。
docker compose --env-file .env -f infra/compose.yaml up -d --build --wait api worker dispatcher
.venv/bin/python scripts/verify_p1d_environment.py
.venv/bin/python scripts/verify_p1d_rag.py
cd apps/web && npm run e2e
```

详见 [P1-D 验收](docs/reports/P1-D_RAG_EVALUATION_ACCEPTANCE.md)、[检索基准](docs/reports/P1-D_RETRIEVAL_BENCHMARK.md) 和 [反馈闭环](docs/reports/P1-D_FEEDBACK_LOOP.md)。当前结论仅覆盖开发/演示环境；专业专家标注和生产认证未验收；P2 模型实测范围见总验收。


## P2 开发环境增量

前轮迁移 `0017_generation_guards`，P2-Closure 升级至 `0018_blind_review`。前轮记录见 [总验收](docs/reports/CORPUSFLOW_FINAL_ACCEPTANCE.md)、[演示指南](docs/demo/DEMO_GUIDE.md)。完整 P2 和生产门禁尚未通过：公网采集受 DNS 限制，复杂版面和真实专家评测未验收。

1. 已有 `.env` 不覆盖。新环境使用 `make install`、`make init-env`，再启动本地依赖。
2. 按 [本地模型说明](tools/semantic/README.md) 用独立锁文件启动已许可的模型；不自动下载大型权重。Docker Desktop 的 `.env` 可设 `EMBEDDING_ENDPOINT=http://host.docker.internal:58110`；宿主测试设为 `http://127.0.0.1:58110`。
3. `docker compose --env-file .env -f infra/compose.yaml up -d --build --wait api worker dispatcher`。只适用于本地开发；init 会升级本地数据库并创建对象桶。
4. `npm --prefix apps/web ci`，`npm --prefix apps/web run dev -- --host 127.0.0.1`，访问 http://127.0.0.1:5173。API 健康检查 http://127.0.0.1:58000/ready。
5. OCR 已进入 Worker 镜像，流水线选择 OCR；默认内置解析仍明确拒绝扫描件。采集主机白名单默认空，审批不自动授权训练用途。

外部生成默认禁用。明确授权后才在被忽略的本地环境文件设置 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`LLM_WORKSPACES`、`LLM_MAX_CALLS`。不要将密钥写入前端、Git 或命令输出。当前授权仅一个自制测试工作空间、最多 10 次、每次 512 输出 Token，已用 2 次；预算持久化，不靠 Worker 重启清零。

```sh
EMBEDDING_ENDPOINT=http://127.0.0.1:58110 .venv/bin/python scripts/verify_p1d_environment.py
make check
.venv/bin/alembic check
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run build
npm --prefix apps/web run e2e
.venv/bin/python scripts/verify_p2_worker_crash.py
.venv/bin/python scripts/verify_local_restore.py
```

完整 Playwright 依赖已保存的受控生成 fixture；新部署没有模型授权/历史答案时，不应伪造数据来通过该用例。可单独运行其他 spec，缺失生成证据明确记录 NOT RUN。故障脚本只操作自己创建的随机数据库、独立队列和 Worker，不停止共享 Worker；备份测试不代表生产 RPO/RTO 或对象桶灾备已验收。


## P2-Closure

新增 `parser=layout` 的实际 Poppler 版面提取、严格采集响应校验、冻结的多人盲评任务与 JSON 导出。规则不自动放宽授权，布局启发式不保证公式/复杂表格语义。参考 [复杂文档评测](docs/reports/P2_COMPLEX_DOCUMENT_BENCHMARK.md)、[采集安全验证](docs/reports/P2_INGEST_SECURITY_VALIDATION.md) 和 [专家操作指南](docs/demo/EXPERT_EVALUATION_GUIDE.md)。

复验命令和依赖见 [最终验收](docs/reports/P2_CLOSURE_ACCEPTANCE.md)。当前已保存模型回答可直接用于评分演示，本轮无新增付费调用。仅有测试账号和自制语料，未完成真实专家评测；不得开放开发认证到公网。
