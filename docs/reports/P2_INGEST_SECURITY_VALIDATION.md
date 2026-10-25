# P2-Closure 采集安全验证

日期：2026-10-25。结论：安全拒绝与受控服务成功路径 **PASS**；合法公网资源成功采集 **BLOCKED**。二者不能互相替代。

## DNS 与连接行为

`P2_CLOSURE_NETWORK_EVIDENCE.json` 保存主机、Docker Worker、配置 DNS 直查和真实请求结果。`api.crossref.org`、`www.rfc-editor.org`、`example.com` 分别解析为 `198.18.0.117`、`.118`、`.123`。直接查询本机配置的 `223.5.5.5` 仍返回保留地址，CNAME 查询无记录。可以确认地址合成现象，不能仅据此归因某个代理软件；本轮没有修改系统 DNS 或代理。

198.18.0.0/15 是基准测试网段，不是合法公网目标。三次真实 HTTPS 采集尝试均在连接前返回 `ACQUISITION_ADDRESS_REJECTED`。这不是把正常全球可达 IP 误判成私网，也不是公网下载成功。[IANA 地址登记表](https://www.iana.org/assignments/iana-ipv4-special-registry)

## 修复及现有约束

- 精确域名白名单、HTTPS/443、IDNA 规范化；拒绝 URL 凭据、片段、控制字符和反斜线。白名单不自动批准许可或用途。
- 解析结果中任一地址不合格即拒绝。阻断回环、RFC1918、链路本地/元数据、CGNAT、ULA、保留、组播、未指定地址，以及 IPv4-mapped、6to4、Teredo 和标准 NAT64 前缀。
- 增加 `168.63.129.16` 显式阻断：它虽可能被标准库视为 global，却是 Azure 平台虚拟地址。[Microsoft 说明](https://learn.microsoft.com/azure/virtual-network/what-is-ip-address-168-63-129-16)
- 验证后的数字 IP 只用于一次连接，不再次解析目标域名；校验实际 peer IP，TLS 仍认证原域名。HTTP Host 保留原域名，不读取环境代理。CNAME 最终地址仍经过同一 IP 门控，重绑定不会触发第二次目标 DNS 查询。
- 全部重定向均拒绝，包括公网到私网、同站重定向。它是保守可用性限制，未声称支持安全重定向跟随。
- DNS 有界线程池及超时；总请求预算覆盖 DNS、连接、TLS、响应头和读取。增加截止计时器、非法 Content-Length、短读检查，保留 20 MiB 上限和压缩传输拒绝。
- 修复 HTTP Connection: close 后 socket 已关闭导致合法完整响应被误报失败的问题。

## 实际测试证据

| 测试 | 结果与范围 |
|---|---|
| `tests/unit/test_acquisition.py` | 26 passed；禁止地址、URL、混合 DNS、普通公网 IPv4/IPv6 校验。正向 IP 单元测试不代表公网连接成功 |
| `test_real_tls_redirect_size_and_truncation` | 自建 HTTPS 真 TLS 字节传输，元数据重定向拒绝、超大/非法长度、短读及慢响应；环境 HTTPS_PROXY 不影响直连 |
| `test_actual_peer_and_hostname_mismatch_are_rejected` | 实际证书名不匹配及 peer IP 不匹配均拒绝 |
| `test_local_https_to_real_asset_minio_and_no_grants` | 随机 PostgreSQL 库、实际 MinIO、不同审核人、真实 HTML 87 字节；1 Asset、0 LicenseGrant、重试无重复 |
| 原有 Web 采集流程 | 真实 API/Outbox/Worker 拒绝内部目标，Web 显示错误；不伪造 Asset |
| 三个公网目标 | BLOCKED；无成功下载，无新用途授权 |

受控服务仅在 pytest 进程内注入测试 DNS、CA 和端口，未给应用增加私网放行参数。它验证协议与业务成功路径，**不证明公网出口可用**。87 字节对象 SHA-256：`f261e82c0f5bb023a25f1fc26be3e0ef77a6d6980ec95b8086fdb4be638ca71a`。安全摘要见 `P2_CLOSURE_RUNTIME_EVIDENCE.json`。

## 尚未完成

公网链路需要正常的可信 DNS/网络出口和许可明确的目标后重新测试。当前不通过代理绕过 IP 门控。透明网络重定向、企业自定义 NAT64、全网 egress 隔离和大规模慢连接压测未验证；生产仍需网络层隔离，应用校验不能替代防火墙。对象写成功而数据库失败的孤儿对象仍需运维清理策略；没有自动扩大授权。
