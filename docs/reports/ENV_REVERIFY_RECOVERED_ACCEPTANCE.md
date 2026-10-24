# 磁盘恢复后的完整环境复验

日期：2026-10-23（Asia/Shanghai）。范围：P0-A 环境、迁移及存储基础能力；对应 NFR-01/06/08、TC-25/26/28 的基础切面。

**结论：本地完整环境复验通过。`BLK-P0B-001` 的镜像获取/重建问题和 `BLK-ENV-002` 的磁盘/Docker 故障在本地复验范围内关闭。远程 CI 未执行，P0-B～P0-F 业务验收仍未执行。**

## 恢复过程与隔离范围

用户释放磁盘空间后，初次检查可用约 96 GiB，但 Docker 引擎仍返回 HTTP 503「Docker Desktop is unable to start」。官方 `docker desktop restart --timeout 60` 无法停止残留进程。正常终止信号后仍残留 PID 25784；经用户明确确认，仅强制终止该 Docker backend，再通过官方 CLI 启动 Docker。

Docker 恢复后，用 `docker start` 启动原有四个 CorpusFlow 服务容器，没有重建旧容器、替换旧镜像或更改旧卷权限。原容器 ID、镜像 ID、卷名称和 `.env`/V3.1 哈希均与故障前记录一致，原服务 `/ready` 返回 200。恢复后重新记录快照，隔离复验前后原容器启动时间也保持一致。

本次新建 BuildKit builder `cf-reverify-recovered`，避免复用上次出现 I/O 错误的 builder。测试项目为 `cf-verify-cacc60d087dd`，使用随机凭证、独立回环端口和全新数据卷。PG/Redis 重新联系官方注册表拉取固定摘要；引擎可复用已有内容层，不宣称所有镜像层均重新下载。MinIO 与 API 使用 `--pull --no-cache` 构建，MinIO 来自固定官方源码及 Go checksum 验证，不读取旧 MinIO 缓存镜像。

## 实际命令与结果

```sh
docker buildx create --name cf-reverify-recovered --driver docker-container --bootstrap
make verify-environment VERIFY_ARGS='--builder cf-reverify-recovered --report-dir docs/reports/ENV_REVERIFY_RECOVERED'
```

整体退出码 **0**，报告为 `status: passed`，13 个步骤退出码均为 0，见 [result.json](ENV_REVERIFY_RECOVERED/result.json)。

| 检查 | 实际结果 | 原始证据 |
|---|---|---|
| 锁定依赖安装 | 成功 | [install.log](ENV_REVERIFY_RECOVERED/install.log) |
| ruff / format / mypy | All checks passed；26 files already formatted；15 source files 无类型错误 | [checks.log](ENV_REVERIFY_RECOVERED/checks.log) |
| 基础单元/契约 | 12 passed, 4 deselected, 1 warning in 1.43s | 同上 |
| PG/Redis 拉取 | 两个固定摘要均 Pulled | [pull.log](ENV_REVERIFY_RECOVERED/pull.log) |
| 最终 MinIO 源码镜像 | 校验、编译、导出成功 | [build-minio.log](ENV_REVERIFY_RECOVERED/build-minio.log) |
| API/init 无缓存构建 | 两个镜像 Built | [build-api.log](ENV_REVERIFY_RECOVERED/build-api.log) |
| 全新卷环境启动 | PG/Redis/MinIO/API Healthy，init Exited 0 | [启动](ENV_REVERIFY_RECOVERED/up.log)、[服务状态](ENV_REVERIFY_RECOVERED/ps.log) |
| 真实 PG 迁移与 S3 集成 | 4 passed, 12 deselected, 1 warning in 4.85s | [migration-and-storage.log](ENV_REVERIFY_RECOVERED/migration-and-storage.log) |
| MinIO 重启后 S3 复验 | 3 passed in 3.39s | [storage-after-restart.log](ENV_REVERIFY_RECOVERED/storage-after-restart.log) |
| 探活故障恢复 | `/ready` 200 → 503 → 200；`/health` 保持 200 | [result.json](ENV_REVERIFY_RECOVERED/result.json) |
| 临时项目停止 | 成功，保留三个测试卷 | [cleanup.log](ENV_REVERIFY_RECOVERED/cleanup.log) |
| 原开发环境保留 | 原容器健康、ID/镜像/卷/启动时间未因隔离测试改变；原 `.env` 与 V3.1 哈希不变 | [前快照](ENV_REVERIFY_RECOVERED/original-state-before.json)、[后快照](ENV_REVERIFY_RECOVERED/original-state-after.json) |

基础测试包含显式测试替身；上述迁移、S3、HTTP 和故障注入使用真实 PostgreSQL/MinIO/API 服务，不以替身替代真实依赖验收。唯一警告为 FastAPI TestClient 对 httpx 的弃用提示，未导致测试失败。

## 覆盖范围

- PostgreSQL：独立随机临时库执行 `upgrade head → alembic check → downgrade base → upgrade head`；仅删除该测试创建的临时库。迁移头仍为 `0001_p0a`。
- S3：两段真实 multipart 上传、读取 SHA-256 一致、启用 versioning、写入第二版本后旧版本字节保持不变、错误凭证被 403 拒绝。
- 重启持久性：第一次写入 sentinel，停止并启动 MinIO 后读取同一 key，字节一致；另外再运行分片与拒绝访问测试。
- 故障探活：停止的只是随机测试项目中的 MinIO；错误码 `DEPENDENCY_UNAVAILABLE`，明细准确记录 PostgreSQL/Redis 为 ok，S3 为 unavailable；恢复后重新返回 ready。
- 运行版本：`DEVELOPMENT.2025-04-22T22-12-26Z`，commit `0d7408fc9969caf07de6a8c3a84f9fbb10a6739e`，Go 1.24.2 linux/arm64，见 [版本记录](ENV_REVERIFY_RECOVERED/minio-version.log)。DEVELOPMENT 表示本项目编译产物，不是 Mock 服务。

## 本轮补充修复

- `scripts/verify_environment.py`：执行前检查本机 Docker socket、Docker 可响应及至少 15 GiB 可用空间；顺序构建 MinIO 和 API；首轮存储测试显式关闭「已存在 sentinel」模式，避免继承外部环境值。
- `infra/docker/minio/Dockerfile`：Go 构建并发设为 2，编译后清理该构建层内的 Go 缓存，减少磁盘负担；不清理用户缓存或卷。
- `tests/integration/test_storage.py`：使用 `contextlib.closing` 关闭 boto3 client；当前 SDK 的 BaseClient 不支持直接作为上下文管理器。
- 更新 README、实施计划、状态、决策与追踪矩阵；旧失败日志保留，以本报告作为最新环境结论。

本轮没有业务 API/schema 变更，没有修改原型或规范原件，没有提交或 push，没有生产环境操作。基线提交仍为 `b1dcb309c7edb1df930a3bc83f5b7be87dba5e75`，修改留在本地供审阅。

## 清理与边界

复验后临时容器与网络已停止/移除；本次确认三个 `cf-verify-cacc60d087dd_*` 测试卷存在并保留，只含合成测试数据。临时凭证文件已按脚本生命周期移除，报告未保存凭证；这些卷不作为后续开发环境。两个本任务创建的 builder 已停止以释放运行资源，未执行全局 prune 或删除旧数据。结束时主机仍有约 90 GiB 可用空间，见 [磁盘记录](ENV_REVERIFY_RECOVERED/host-disk-after.log)。

本次通过的是本机 ARM64 上、与 CI 共用入口的完整流程。由于用户禁止 push，GitHub Actions 未重跑，历史远程红灯不会因此自动变绿；AMD64、生产部署、安全升级与旧卷升级也未验收。P0-B 的 IAM/Policy 测试与报告不能由本报告替代。
