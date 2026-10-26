# Agent 2 数据集页面

由 `src/app/modules.tsx` 自动发现，路由 `#/datasets/cpt|sft|dpo`。默认生成目录，所有查询使用公共客户端和冻结DTO。正式页面不导入测试数据；API失败显示错误。

目录、revision、dataset_id、version、tab、split、q、offset、sample_id 保存在URL；版本固定后才请求概览/样本/manifest。下载使用公共二进制下载工具；指定split全部导出，文本搜索不影响下载范围。

构建入口要求服务端确认的admin/engineer角色，并一次性切换URL至workspace、清理生成目录实体ID。CPT/SFT复用DatasetPage，DPO复用DpoPage。发布后刷新快照，构建页保留实际成功结果。

本地验证（在 apps/web 目录）：

```powershell
npm ci --no-audit --no-fund
npm run typecheck
npm run lint
npm run build
npx playwright test --config src/features/training-datasets/playwright.config.ts
```

Playwright独占5192端口，不复用共享服务；仅浏览器测试用HTTP拦截提供冻结契约样例，明确不代表真实后端验收。覆盖版本选择/刷新、筛选/分页/URL恢复、SFT消息顺序、DPO移动端、错误下载、快照过期、角色和CPT构建映射。结果和截图写入忽略的 `.local/training-center/`。

真实后端需 Agent 1 注册 `corpusflow.api.v1.training_center.router`；workspace读取还需要实际已发布版本，manifest需要可访问的对象存储，导出需要真实training授权。未知Tokens保持暂无统计。
