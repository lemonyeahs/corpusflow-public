# M0 开发请求样例

使用方式、边界、责任方和字段待确认项见 [M0 接入说明](../../../../../docs/plans/TRAINING_CENTER_M0_INTEGRATION.md)。

- 来源：`fixtures.ts` 手工编写；版本 `m0-fixture-v1`；seed=null，没有随机生成。
- `fixtureProvenance` 保留创建方式；样例不属于真实上传/清洗历史。
- 仅 `import.meta.env.DEV && VITE_TC_FIXTURES === "true"` 启用；默认关闭。
- success/empty/error 是显式场景，不能根据接口失败切换。
- 认证、workspace、写操作和下载不拦截。未覆盖端点继续网络请求。
- Agent 2/3/4 提供样例后由 Agent 1 整合；不要在页面里新增统计常量。
