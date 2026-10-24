# CorpusFlow

当前交付包含 **P0-A～P0-G 的本地可验收真实业务闭环**：FastAPI、版本化迁移、空间与用途授权、真实字节上传、异步 Run、PDF/HTML 解析、SFT 构建审核、JSONL/Manifest 数据集物化、不可变发布、签名下载、血缘和审计。V3.1 仍是独立浏览器 DEMO，不能代表正式 Web UI 已完成。

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

P0-A 回滚：停止 API，备份开发数据库后可在本地执行 `uv run --locked alembic downgrade base`，只回退版本标记。原型原件未修改，无需回滚。没有自动删卷或生产迁移命令。

## 目录与边界

- `apps/api/src/corpusflow`：API、配置/错误/日志、DB、业务路由与策略、真实依赖探测；`modules/*` 保留后续扩展边界。
- `apps/api/alembic`：版本化迁移。业务 Service 持有事务边界，禁止 ORM event 复制业务策略。
- `apps/web`：P0-F 前端对接边界；`docs/prototype` 为原型只读参考副本。
- `infra`：PostgreSQL 16、Redis、MinIO、API、Worker 和 Outbox Dispatcher 的本地 Compose。
- `tests`：单元、契约、独立临时 PostgreSQL 迁移测试；`scripts/verify_business_loop.py` 覆盖 P0-B～F 业务门禁。
- `docs/plans`：现状、分阶段任务、追踪矩阵、待确认决策。
- `docs/reports/P0_DATASET_MATERIALIZATION_ACCEPTANCE.md`：P0-G 数据集物化、发布和交付证据。

分层：Router → Application Service → Domain Policy → Repository / Adapter。当前开发身份 session、内置 parser、Celery/Outbox 和本地数据集物化是受控本地实现；生产 OIDC、外部 parser/generation 和正式 Web UI 仍未接入。请求 JSON 日志不能替代不可变业务审计。

项目仓库：[lemonyeahs/corpusflow](https://github.com/lemonyeahs/corpusflow)（私有）。默认分支为 `main`。P0-A 验收报告记录首次发布前的本地验收状态；远程 CI 结果以 GitHub Actions 为准。首次远程运行的镜像拉取限制见 [GitHub 上传记录](docs/reports/GITHUB_UPLOAD.md)。

当前完整流程已在本机 ARM64 验证，远程 CI 未重跑。基础镜像固定摘要，MinIO 固定源码提交及下载包校验值；AMD64 兼容与生产镜像安全评估未完成，详见验收报告。
