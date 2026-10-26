import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import { AriaComponent, GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/esm/core";
import type { EChartsOption } from "echarts";
import type { Distribution, TimeSeries } from "../../../contracts/training-center";
import { ChartFrame, EmptyState } from "../../../ui";
import { sourceLabels, unitLabels } from "../../training-home/components/format";
import styles from "../explorer.module.css";

echarts.use([BarChart, LineChart, PieChart, AriaComponent, GridComponent, TooltipComponent, LegendComponent, SVGRenderer]);
const colors = ["#298f78", "#8fb8ca", "#e6c18e", "#b6a5cd", "#d9e2df"];
const measureLabels: Record<string, string> = { segment_char_length: "片段字符长度", segment_language: "片段语言", file_source_kind: "文件来源类别" };
function Chart({ option, label }: { option: EChartsOption; label: string }) {
  return <div role="img" aria-label={label}><ReactEChartsCore echarts={echarts} option={{ animation: false, color: colors, aria: { enabled: true }, textStyle: { fontFamily: '"Segoe UI","Microsoft YaHei",sans-serif' }, ...option }} opts={{ renderer: "svg" }} style={{ height: 240, width: "100%" }} notMerge /></div>;
}
export function DistributionChart({ title, data, kind = "bar" }: { title: string; data: Distribution; kind?: "bar" | "donut" }) {
  const label = (key: string, fallback: string) => sourceLabels[key] || ({ zh: "中文", en: "英文", unknown: "未知" } as Record<string, string>)[key] || fallback;
  const labels = data.buckets.map(bucket => label(bucket.key, bucket.label));
  const option: EChartsOption = kind === "donut" ? {
    tooltip: { trigger: "item", renderMode: "richText" },
    series: [{ type: "pie", radius: ["44%", "67%"], center: ["50%", "46%"], label: { show: false }, data: data.buckets.map((bucket, index) => ({ name: labels[index], value: bucket.count })) }],
  } : {
    grid: { left: 42, right: 12, top: 16, bottom: 45 }, tooltip: { trigger: "axis", renderMode: "richText" },
    xAxis: { type: "category", data: labels, axisLabel: { color: "#81909d", fontSize: 10, interval: 0, overflow: "truncate", width: 65 }, axisTick: { show: false } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#eef2f4" } } },
    series: [{ type: "bar", barMaxWidth: 35, data: data.buckets.map(bucket => bucket.count), itemStyle: { borderRadius: [4, 4, 0, 0] } }],
  };
  return <ChartFrame title={title} measure={measureLabels[data.measure] || data.measure} unit={unitLabels[data.unit]}>
    {!data.total_count ? <EmptyState description="暂无该范围的分布数据" /> : <><Chart option={option} label={`${title}，总计 ${data.total_count} ${unitLabels[data.unit]}`} /><ul className={styles.legend}>{data.buckets.map((bucket, index) => <li key={bucket.key}><i style={{ background: colors[index % colors.length] }} />{labels[index]}<b>{bucket.count.toLocaleString("zh-CN")}</b><span>{bucket.ratio == null ? "—" : `${(bucket.ratio * 100).toFixed(1)}%`}</span></li>)}</ul></>}
  </ChartFrame>;
}
export function TrendChart({ data, reason }: { data: TimeSeries | null; reason: string }) {
  // Display at most the last 30 UTC days supplied by the server; never fabricate missing dates.
  const end = data ? new Date(data.to).getTime() : 0;
  const endDay = Math.floor(end / 86_400_000) * 86_400_000;
  const start = Math.max(data ? new Date(data.from).getTime() : 0, endDay - 29 * 86_400_000);
  const points = data?.points.filter(point => new Date(point.date).getTime() >= start && new Date(point.date).getTime() <= end) || [];
  return <ChartFrame title="接入趋势 · 近 30 天" measure="接入时间" unit={data ? `${unitLabels[data.unit]} · ${data.timezone}` : "UTC"}>
    {!data || !points.length ? <EmptyState description={reason === "ingested_at_missing" ? "缺少真实接入时间，暂无趋势统计" : "暂无接入记录"} /> : <><Chart label="接入数量趋势" option={{
      grid: { left: 45, right: 18, top: 20, bottom: 35 }, tooltip: { trigger: "axis", renderMode: "richText" },
      xAxis: { type: "category", data: points.map(point => point.date), axisLabel: { color: "#81909d", fontSize: 10 }, axisTick: { show: false } },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#eef2f4" } } },
      series: [{ type: "line", data: points.map(point => point.count), smooth: false, symbolSize: 5, areaStyle: { color: "#e9f6f1" }, lineStyle: { width: 2 } }],
    }} /><p className={styles.note}>{points[0].date} — {points.at(-1)?.date} · {data.timezone}</p></>}
  </ChartFrame>;
}
