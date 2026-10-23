# catalog

P0-A 仅预留边界，无业务实现或路由。后续按 router → application service → domain policy → repository/adapter 分层。权限和用途判定集中在 identity/authorization，禁止在 Worker 或 UI 中复制规则。
