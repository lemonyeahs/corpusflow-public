# 数据台模块

默认入口 `index.tsx` 自动挂载到 `#/data/:format`，无需改 App.tsx。公共 DTO 从 `../../contracts/training-center` 导入。

- `queries.ts`：文件入口固定快照，再查询统计、数据集和详情。
- `components/StatisticsCharts.tsx`：懒加载 ECharts，分布来自完整响应，与当前页行数无关。
- `components/FileDetail.tsx`：URL 驱动的详情抽屉。
- `components/ComparisonView.tsx`：导出 `ComparisonView({comparison: ComparisonResponse})` 供 Agent 3 接入页复用。传入真实响应或显式契约样例；组件保留文本换行、校验 before/after 的 record_id，不生成处理结果。

```tsx
import { ComparisonView } from "../data-explorer/components/ComparisonView";
// comparison 已由调用方查询、核验授权与 scope。
<ComparisonView comparison={comparison} />
```

数据台 URL 扩展：`file_id` 打开详情，`detail_tab=detail|comparison` 选择标签，`record_id` 指向该文件的具体处理记录；其余参数沿用契约。跨页面入口可使用 `#/data/txt?catalog=workspace&file_id=<file>&detail_tab=comparison&record_id=<record>`，只有同一目录且有效的统计 revision 才能继续携带。

工作空间处理批次可能包含多个文件，当前 FileDetail DTO 没有默认对比 record/step 映射。未给 record_id 时不展示批次任意记录；给定后从 summary 中查找包含该记录的最新成功/部分成功步骤，再请求 comparison。Agent 2/3 需补齐文件到记录的可靠入口，详见[协作事项](../../../../../docs/reports/TRAINING_CENTER_M1_SHELL_EXPLORER.md)。
