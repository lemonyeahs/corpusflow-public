# MinIO 本地源码镜像

原 Quay/Docker Hub 二进制引用无法拉取，改为从 [MinIO 官方源码](https://github.com/minio/minio/tree/0d7408fc9969caf07de6a8c3a84f9fbb10a6739e) 构建。保持原部署的 `RELEASE.2025-04-22T22-12-26Z` 代码版本，不替换 S3 实现。

| 项目 | 固定值 |
|---|---|
| 官方 tag 对象 | `f19c534b9f457773dcd043d977433e1a71525c3b` |
| tag 指向的 commit | `0d7408fc9969caf07de6a8c3a84f9fbb10a6739e` |
| 官方 codeload tar.gz SHA-256 | `7eb30a913fea30f18069abf194e1e78e4983b558cc526911ae1c11396a9859a5` |
| Go | 1.24.2，基础镜像摘要见 Dockerfile |
| 运行基底 | Python 3.12.13 slim，与 API 相同摘要；Python 用于健康检查 |

构建通过 `ADD --checksum` 校验源码，通过 Go checksum 服务及 `go mod verify` 校验依赖，再执行只读 module 编译。固定 `GOTOOLCHAIN=local`，不自动下载其他 Go 版本。源码包、LICENSE、NOTICE 保存在镜像 `/usr/share/minio`。ReleaseTag 使用 DEVELOPMENT 标记本项目源码构建，不将其冒充官方预编译镜像或 Mock 服务。

最终 Dockerfile 保留原 MinIO 镜像的 root UID，以兼容已有 root-owned 数据卷；不在入口脚本执行 chown、不更改旧卷权限。API 仍使用非 root 用户。Go 构建并发限制为 2，并在编译完成后清理构建层内的 Go 缓存。磁盘恢复后的最终镜像及全新卷环境已通过本地 ARM64 复验，详见 [最新报告](../../../docs/reports/ENV_REVERIFY_RECOVERED_ACCEPTANCE.md)；这不代表旧卷升级已验收。

仅限当前本地开发/测试。上游 [README](https://github.com/minio/minio#source-only-distribution) 说明社区版源码分发；当前仓库已归档。此修复沿用现有 MinIO 的 AGPLv3 授权，不签发任何语料许可。生产安全升级、旧卷升级和软件分发义务未在本轮验收。
