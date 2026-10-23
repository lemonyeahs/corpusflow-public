# GitHub 上传记录

日期：2026-10-23。

- 仓库：[lemonyeahs/corpusflow](https://github.com/lemonyeahs/corpusflow)，私有。
- 初始提交：`b8dae8da441ea3c469f8abd53e0ab222fe1db104`，已推送至默认分支 `main`。
- 此前没有 Git 历史，本次为首次提交，直接进入 `main`，没有创建或合并 PR。
- `.env`、虚拟环境和缓存未纳入版本管理。原型与规范原件保留。
- GitHub CLI 已通过账号授权；本仓库使用其凭证助手，不在仓库保存令牌。

## 首次远程 CI

[运行 39926401581](https://github.com/lemonyeahs/corpusflow/actions/runs/39926401581) 的依赖安装、环境初始化和 `make check` 成功。`make up` 拉取 MinIO 镜像失败，后续迁移集成测试及 `/ready` 检查被跳过，整次运行失败。

真实失败输出：

```text
minio Error unauthorized: access to the requested resource is not authorized
Error response from daemon: unauthorized: access to the requested resource is not authorized
make: *** [Makefile:8: up] Error 1
```

本机执行 `docker buildx imagetools inspect quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z` 同样返回 `401 Unauthorized`。本地已有镜像的运行成功不能证明全新环境可拉取镜像。本记录补充 P0-A 本地验收报告，不将远程集成测试标记为通过。

后续需确认可合法访问的 MinIO 镜像来源或镜像仓库凭证，再固定可验证的摘要并重新执行 CI。此次未更换存储实现、删除数据卷或进入 P0-B，也未为 CI 配置私有镜像凭证。
