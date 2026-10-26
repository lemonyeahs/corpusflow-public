# Agent 2 数据集页面

由 `src/app/modules.tsx` 自动发现，路由 `#/datasets/cpt|sft|dpo`。默认生成目录，所有查询使用公共客户端和冻结DTO。正式页面不导入测试数据；API失败显示错误。

目录、revision、dataset_id、version、tab、split、q、offset、sample_id 保存在URL；版本固定后才请求概览/样本/manifest。样本详情使用独立接口恢复抽屉，不依赖当前分页。下载使用公共二进制下载工具；split和文本搜索共同过滤，导出全部匹配结果，不发送offset/limit。切换空间/目录/快照及卸载时中止下载。

构建入口要求服务端确认的admin/engineer角色，并一次性切换URL至workspace、清理生成目录实体ID。CPT/SFT复用DatasetPage，DPO复用DpoPage。发布后刷新快照，构建页保留实际成功结果。

本地验证（在 apps/web 目录）：

```powershell
npm ci --no-audit --no-fund
npm run typecheck
npm run lint
npm run build
npx playwright test --config src/features/training-datasets/playwright.config.ts
```

Playwright独占5192端口，不复用共享服务；仅浏览器测试用HTTP拦截提供冻结契约样例，明确不代表真实后端验收。10项测试覆盖版本选择/刷新、筛选/分页/URL恢复、SFT消息顺序、DPO移动端、成功/失败下载、详情深链接、manifest/空版本、快照过期、角色、CPT构建映射和旧DPO校验/发布请求。结果和截图写入忽略的 `.local/training-center/`。

基线acb7ce0已注册真实router；workspace读取需要实际已发布版本，manifest需要可访问的对象存储，导出需要真实training授权。未知Tokens保持暂无统计。Agent 1的统一快照接口仍在开发：workspace血缘链接暂不传目录revision，图接口建立独立快照；generated链接保留发布revision。
