# 数据台模块

默认入口 `index.tsx` 自动挂载到 `#/data/:format`，无需改 App.tsx。公共 DTO 从 `../../contracts/training-center` 导入。

- `queries.ts`：文件入口固定快照，再查询统计、数据集和详情。
- `components/StatisticsCharts.tsx`：懒加载 ECharts，分布来自完整响应，与当前页行数无关。
- `components/FileDetail.tsx`：URL 驱动的详情抽屉。
- `components/FileProcessingSummary.tsx`：沿文件详情的显式运行引用加载摘要，校验同快照、run_id 和文件输入引用；无引用时不查询任意运行。
- `components/ComparisonView.tsx`：导出 `ComparisonView({comparison: ComparisonResponse})` 供 Agent 3 接入页复用。传入真实响应或显式契约样例；组件保留文本换行、校验 before/after 的 record_id，不生成处理结果。

```tsx
import { ComparisonView } from "../data-explorer/components/ComparisonView";
// comparison 已由调用方查询、核验授权与 scope。
<ComparisonView comparison={comparison} />
```

数据台 URL 扩展：`file_id` 打开详情，`detail_tab=detail|comparison|processing` 选择标签，`record_id` 指向该文件的具体处理记录；其余参数沿用契约。跨页面入口可使用 `#/data/txt?catalog=workspace&file_id=<file>&detail_tab=comparison&record_id=<record>`，只有同一快照服务发行的有效 revision 才能继续携带。

两种 catalog 的文件对比统一调用冻结契约已有的 `/training-center/files/{file_id}/comparison`。Agent 2 在服务端验证 file→run→step→record 映射，调用 Agent 3 的真实对比查询；客户端不再从 summary 选取步骤。workspace 无 processing_summary_ref 时保持不可用；响应还须匹配详情引用的 run_id，前后 record_id 一致，显式 record_id 与响应一致。无默认映射由服务端返回 COMPARISON_NOT_AVAILABLE。

新模块可复用 `src/api/training-center.ts` 的 `scopedRequest`：第六个参数传 `{expectedScope, client}`，核验完整 Scope 并在当前 QueryClient 中记住同 revision 的 as_of/metric_definition_version。旧 training-home/api 导出兼容保留。范围元数据随目录刷新、退出或换空间清除，不包含 token。

当前 workspace 图仍有独立快照服务，公共导航及本模块血缘链接不沿用目录 token，并显示重新获取快照的说明。统一服务交付前不能声称跨图/目录共用快照。接口请求和各方接入条件见 [M2 请求](../../../../../docs/plans/TRAINING_CENTER_M2_INTEGRATION_REQUESTS.md)，真实与受控测试结果见 [M2 公共接入报告](../../../../../docs/reports/TRAINING_CENTER_M2_SHELL_INTEGRATION.md)。
