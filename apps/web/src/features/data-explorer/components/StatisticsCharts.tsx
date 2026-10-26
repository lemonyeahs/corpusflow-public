import type { FormatStatsResponse } from "../../../contracts/training-center";
import { DistributionChart, TrendChart } from "./Charts";
import styles from "../explorer.module.css";
export default function StatisticsCharts({ stats }: { stats: FormatStatsResponse }) {
  return <div className={styles.charts}><div className={styles.trend}><TrendChart data={stats.ingestion_trend} reason={stats.availability.ingestion_trend} /></div><DistributionChart title="片段长度分布" data={stats.length_distribution} /><DistributionChart title="片段语言分布" data={stats.language_distribution} kind="donut" /><DistributionChart title="文件来源分布" data={stats.source_distribution} kind="donut" /></div>;
}
