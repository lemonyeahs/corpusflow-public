# CorpusFlow

当前交付为 **P0-A 工程骨架**：FastAPI、真实依赖探活、数据库迁移基线、配置与错误契约、测试和 CI。上传、鉴权、许可证、Worker、发布等业务功能尚未实现。V3.1 是独立浏览器 DEMO，不能代表后端能力。

## 本地启动

前置：Docker Engine / Docker Desktop 与 Compose、Python 3、uv、make。服务仅绑定本机回环地址。本阶段拒绝 staging/production 配置。

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

无 `CF_TEST_ADMIN_DATABASE_URL` 时集成测试显示 SKIP，不算通过。生产数据库禁止运行上述测试。初始化迁移 `0001_p0a` 仅建立 Alembic 版本基线，不预建 IAM/业务表；后续追加迁移。

```sh
make down                 # 停服务并保留所有 named volumes
```

P0-A 回滚：停止 API，备份开发数据库后可在本地执行 `uv run --locked alembic downgrade base`，只回退版本标记。原型原件未修改，无需回滚。没有自动删卷或生产迁移命令。

## 目录与边界

- `apps/api/src/corpusflow`：API、配置/错误/日志、DB 与真实依赖探测；`modules/*` 为后续阶段边界。
- `apps/api/alembic`：版本化迁移。业务 Service 持有事务边界，禁止 ORM event 复制业务策略。
- `apps/web`：P0-F 前端对接边界；`docs/prototype` 为原型只读参考副本。
- `infra`：PostgreSQL 16、Redis、MinIO 和 API 的本地 Compose；无正式 Worker。
- `tests`：单元、契约、独立临时 PostgreSQL 迁移测试。
- `docs/plans`：现状、分阶段任务、追踪矩阵、待确认决策。
- `docs/reports/P0-A_ACCEPTANCE.md`：实际执行证据与限制。

分层：Router → Application Service → Domain Policy → Repository / Adapter。P0-A 没有业务写路由，也没有 MockAdapter、假登录或假任务。用途许可默认拒绝、身份隔离、审计事件将在 P0-B 实现；请求 JSON 日志不能替代不可变业务审计。

项目仓库：[lemonyeahs/corpusflow](https://github.com/lemonyeahs/corpusflow)（私有）。默认分支为 `main`。P0-A 验收报告记录首次发布前的本地验收状态；远程 CI 结果以 GitHub Actions 为准。首次远程运行的镜像拉取限制见 [GitHub 上传记录](docs/reports/GITHUB_UPLOAD.md)。

当前镜像与 CI 在 ARM64 验证。PG/MinIO 使用固定摘要；x86 兼容与生产镜像安全评估未完成，详见验收报告。
