# 玄知大模型 Web（P0-H）

训练数据中心已建立 HashRouter 工作区壳，契约冻结为 1.0.0。Agent 1 的 M1 首页、格式数据台、文件详情与对比展示已实现；真实业务接口联调属于 M2。接入、CPT/SFT/DPO、血缘由各模块入口独立挂载，现有页面保留在高级工具分组。公共入口见 [M0 接入说明第 10 节](../../docs/plans/TRAINING_CENTER_M0_INTEGRATION.md#10-m0-冻结后的接入入口取代上述草案状态)，新页面调用约定和当前限制见 [M1 接入与交付说明](../../docs/reports/TRAINING_CENTER_M1_SHELL_EXPLORER.md)。

基线 acb7ce0 已接通 generated 9 个查询接口。后续公共 scope 校验、文件限定对比、处理摘要标签及尚未到位的 workspace/处理依赖见 [M2 公共接入报告](../../docs/reports/TRAINING_CENTER_M2_SHELL_INTEGRATION.md)；此报告取代 M1 中由客户端选择处理步骤的接入方式。

这是 玄知大模型 的 TypeScript + React + Vite Web 工作台。核心业务页面通过 `src/api/client.ts` 调用真实 FastAPI，不使用固定业务演示数据；V3.1 HTML 原型保留在 `docs/prototype/`。

## 本地启动

先启动真实后端依赖和服务：

```bash
docker compose --env-file .env -f infra/compose.yaml up -d postgres redis minio init api worker dispatcher
```

再启动 Web：

```bash
cd apps/web
npm ci
npm run dev
```

浏览器访问 <http://127.0.0.1:5173>。Vite 默认将 `/api` 代理到 `http://127.0.0.1:58000`；可通过 `API_PROXY_TARGET` 配置自己的后端，通过 `VITE_API_BASE_URL` 指定部署后的公开反向代理地址。其他 worktree 已占用端口时使用 `npm run dev -- --port <空闲端口> --strictPort`。

## 检查与测试

```bash
npm run typecheck
npm run lint
npm run build
npm run test:m0
npm run e2e
```

`npm run e2e` 需要本地 Docker API、Worker、PostgreSQL、Redis、MinIO 和 Playwright Chromium。测试会创建隔离开发身份和 workspace，写入本地测试数据，不访问生产环境。

`npm run test:m0` 使用独立端口、Chrome 和 Playwright 测试响应检查前端壳，不需要数据库，也不等同于真实后端验收。旧全流程测试的导航定位需在后续回归中适配新高级分组。

## 页面边界

已接入真实 API 的页面包括登录/空间、数据接入、资产和结构化片段、处理 Run、质量审核、SFT/DPO 构建、发布下载、血缘和系统审计。生产 OIDC、AI 智能采集、外部解析服务、正式模型生成和 Parquet 导出仍显示为 DEMO/未接入；DPO 页面仅准备偏好数据，不执行 DPO 训练。

## 纯前端演示

运行 `npm run demo`，打开 `http://127.0.0.1:5173/#/home?catalog=workspace`。此模式自动进入独立演示身份，不读取或改写真实登录 session；Vite 不配置 API 代理，所有 API 请求在前端拦截，未知路径和写入/上传/下载均明确拒绝，不回退后端。生产构建与普通 `npm run dev` 不启用此模式。

演示脚本 `src/dev/training-center/demo.ts` 提供 1200 个多格式文件及 300000 条逻辑训练记录（CPT 140000、SFT 105000、DPO 55000）。样本按页生成；支持来源/格式/语言筛选、样本搜索、切分与分页、文件详情、清洗对比、版本清单。指标、Tokens、趋势、处理记录及活动均为人工设计的界面展示数据，不代表实际后端执行或质量评估。构建、发布和下载入口在演示模式停用，真实业务模式保持原逻辑。

验证：`node scripts/check-demo.mjs` 覆盖计数、首尾与越界分页、筛选、对比、禁止网络回退及写入/上传/下载阻断；另运行 typecheck、lint、build。普通构建产物不得包含 `frontend-demo.invalid` 或演示正文。
