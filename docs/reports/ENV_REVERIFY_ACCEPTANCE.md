# 镜像来源修复与完整环境复验

> 历史失败记录：后续磁盘及 Docker 恢复后，本地完整环境已通过复验，详见 [最新独立报告](ENV_REVERIFY_RECOVERED_ACCEPTANCE.md)。以下保留当次失败原文，不作为当前环境状态。

日期：2026-10-23（Asia/Shanghai）。对应 TASK-CF-001 前置环境修复及 `BLK-P0B-001`。

**结论：未通过完整环境复验。官方源码首次构建成功；整套环境无缓存构建因存储 I/O 错误失败。新增阻塞 `BLK-ENV-002`，P0-B～P0-F 未开始。**

## 镜像来源修复

官方 Docker Hub 的原版本也返回访问拒绝。上游 [官方 README](https://github.com/minio/minio#source-only-distribution) 说明社区版仅提供源码。此次保持原 MinIO 代码版本，从官方标签解析至固定 commit，构建中强制校验下载包和 Go 依赖，不使用第三方镜像站或 Mock。

- tag：`RELEASE.2025-04-22T22-12-26Z`。
- tag 对象：`f19c534b9f457773dcd043d977433e1a71525c3b`。
- commit：`0d7408fc9969caf07de6a8c3a84f9fbb10a6739e`。
- 源码包 SHA-256：`7eb30a913fea30f18069abf194e1e78e4983b558cc526911ae1c11396a9859a5`。
- Go/Python/uv/Redis 和原 PG 基础镜像均固定摘要，见 Dockerfile 和 Compose。

使用新建的 `cf-minio-reverify` BuildKit builder 首次执行：

```sh
docker buildx build --builder cf-minio-reverify --pull --no-cache --load \
  --progress plain -t corpusflow-verify-minio:source infra/docker/minio
```

退出码 0，日志包含 `all modules verified`、编译及镜像导出成功，见 [首次源码构建日志](ENV_REVERIFY_MINIO_BUILD.log)。首次构建的 runtime 使用非 root UID；随后检查发现旧 MinIO 数据卷为 `0:0 755`，最终 Dockerfile 恢复与旧镜像相同的 root UID，避免隐式更改已有卷权限。因此首次构建仅证明源码获取和编译链可用，不代表最终完整配置验收通过。

## 完整环境复验

实际命令：

```sh
make verify-environment VERIFY_ARGS='--builder cf-minio-reverify --report-dir docs/reports/ENV_REVERIFY'
```

隔离项目：`cf-verify-dd9e04b3ea32`；使用临时随机凭证及独立回环端口。未使用现有开发 `.env` 的凭证创建测试环境。

| 步骤 | 真实结果 | 证据 |
|---|---|---|
| `uv sync --locked` | 通过 | [install.log](ENV_REVERIFY/install.log) |
| ruff / format / mypy | 通过；26 文件格式检查，15 源文件类型检查 | [checks.log](ENV_REVERIFY/checks.log) |
| 基础单元/契约测试 | 12 passed, 4 deselected, 1 warning | 同上 |
| PG/Redis 注册表拉取 | 通过；引擎可能复用已有内容层，未声称这些层全部重新下载 | [pull.log](ENV_REVERIFY/pull.log) |
| Compose `build --pull --no-cache` | 失败；Go 编译和 BuildKit metadata 写入 I/O error | [build.log](ENV_REVERIFY/build.log) |
| 新环境 `up`、真实迁移、S3 分片/版本/鉴权、重启持久性、HTTP 故障恢复 | **未执行**，构建失败即停止 | [result.json](ENV_REVERIFY/result.json) |
| 临时项目 `down` | 退出码 0；尚未执行 `up` | [cleanup.log](ENV_REVERIFY/cleanup.log) |

`result.json` 的 `retained_test_volumes` 为脚本预先列出的卷名称，不证明这些卷已创建；本次未到 `up` 阶段。静态检查通过不能替代新增的真实 S3 测试通过。先前的 P0-A 迁移结果不算本次迁移结果。

## BLK-ENV-002：本机存储资源及 Docker 不可用

构建失败输出摘录：

```text
can't create $WORK/b721/_pkg_.a: open $WORK/b721/_pkg_.a: input/output error
error committing tiy7w08f8hppd35xyf8bd7zz9: write /var/lib/buildkit/runc-overlayfs/metadata_v2.db: input/output error
```

随后 `df -h /Users/leon/Desktop/data` 显示数据分区 Capacity 为 100%，可用约 3.1 GiB，见 [磁盘状态](ENV_REVERIFY/host-disk.log)。后续 `docker system df` 和 `docker ps` 均返回：

```text
Error response from daemon: Docker Desktop is unable to start
```

此次源码编译及重复无缓存构建增加了本机存储负担；以上现象与存储资源不足一致。未进行文件系统修复或根因取证，不能断言 Docker 数据已损坏，也不能保证旧服务仍正常运行。按严重失败/数据风险停止条件暂停，不再构建、重启 Docker、清理未知镜像/缓存或操作既有数据卷。

现有开发 `.env`、V3.1 原件及留存副本哈希不变，见 [文件保留证据](ENV_REVERIFY/file-preservation.json)。原容器 ID、启动时间及卷名称已在 [复验前快照](ENV_REVERIFY/original-state-before.json) 记录；因 Docker 随后不可用，未完成容器状态的复验后比较。

## 实际代码和配置修改

- `infra/docker/minio/Dockerfile`：官方固定源码构建、摘要校验、许可证及源码留存。
- `infra/compose.yaml`：改为构建 MinIO；Redis 固定摘要；支持独立环境文件和端口覆盖。
- `infra/docker/Dockerfile`：Python/uv 固定摘要。
- `scripts/init_env.py`：提取生成函数，保留独占写入和 0600 权限，不覆盖已有 `.env`。
- `scripts/verify_environment.py`、`Makefile`：可重复隔离复验入口；报告含实际退出码，错误输出替换本轮随机凭证；临时项目停止不删卷。
- `tests/integration/test_storage.py`：新增真实 multipart SHA-256、版本保留、错误凭证拒绝、重启持久性测试；本轮尚未执行。
- `.github/workflows/ci.yml`：改用同一复验入口并保留日志 artifact；未 push，远程 CI 未运行。
- `.gitignore`、`.dockerignore`：排除本地复验目录。
- 构建说明、计划状态和本报告：保存真实成功/失败边界。

没有新增业务 API、业务迁移或 P0-B 代码，没有修改原型和规范原件，没有创建提交或 push，没有操作生产环境。

## 恢复条件与下一次执行

1. 先由环境负责人释放或增加本机可用磁盘空间。建议为首次源码编译预留至少 15 GiB 的空间预算；这是保守运行预算，不是实测峰值。不要删除 Docker 数据盘或用户卷。当前 Docker 不可用，不能安全地通过 daemon 回收本轮 builder 缓存。
2. Docker 恢复后先核对原 `corpusflow-p0a` 服务、数据卷及 `/ready`。本轮创建的 `cf-minio-reverify` builder 和 `corpusflow-verify-minio:source` 镜像属于可重建测试产物；只清理明确属于本轮的资源，不执行全局 prune。
3. 后续复验应避免并发重复编译并控制构建临时存储占用。保留本次失败证据，使用新的报告目录重跑 `make verify-environment`。仅在本机 Docker context 使用当前脚本。
4. 构建、完整启动、真实迁移及新增 S3/HTTP 测试全部通过后，才关闭前置阻塞。远程 CI 因本轮禁止 push 仍待另行授权验证。

当前不可将 `BLK-P0B-001` 标为完全关闭：源码获取已找到可行路径，但完整环境未重建成功，新增 `BLK-ENV-002` 必须先解决。
