import { useEffect, useRef, useState } from "react";
import { api, ApiError, type ApiContext } from "../api/client";
import type { Asset, OperatorDefinition, PipelineRun, ProcessingArtifact } from "../types";
import { Badge, Card, Empty, ErrorBox, Field, Page, formatTime } from "../components";

export function ProcessingPage({ ctx }: { ctx: ApiContext }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [operators, setOperators] = useState<OperatorDefinition[]>([]);
  const [artifacts, setArtifacts] = useState<Record<string, ProcessingArtifact[]>>({});
  const [logs, setLogs] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [parserKind,setParserKind] = useState('builtin');
  const [config, setConfig] = useState('{"operators":[{"key":"builtin.clean","config":{}},{"key":"builtin.deduplicate","config":{}},{"key":"builtin.quality","config":{}}]}');
  const polling = useRef<number | undefined>(undefined);

  useEffect(() => {
    void Promise.all([api.assets(ctx, 0, 100), api.operators(ctx)])
      .then(([assetResult, operatorResult]) => {
        setAssets(assetResult.items);
        setOperators(operatorResult.items);
      })
      .catch(() => setError("资产或算子注册表加载失败"));
    return () => window.clearTimeout(polling.current);
  }, [ctx]);

  async function refreshRuns(sourceRuns = runs) {
    if (!sourceRuns.length) return;
    const result = await Promise.all(sourceRuns.map(run => api.run(ctx, run.run_id)));
    setRuns(result);
    for (const run of result) {
      const [log, artifactResult] = await Promise.all([
        api.runLogs(ctx, run.run_id),
        api.runArtifacts(ctx, run.run_id),
      ]);
      setLogs(prev => ({ ...prev, [run.run_id]: log.items.map(item => `[${item.level}] ${item.message}`) }));
      setArtifacts(prev => ({ ...prev, [run.run_id]: artifactResult.items }));
    }
    if (result.some(run => ["queued", "running"].includes(run.status))) {
      polling.current = window.setTimeout(() => void refreshRuns(result), 1500);
    }
  }

  async function create() {
    setBusy(true);
    setError("");
    try {
      const parsed = JSON.parse(config) as Record<string, unknown>;
      const result = await api.createRuns(ctx, { asset_ids: selected, config: {...parsed,parser:parserKind} });
      const createdRuns = result.accepted.map(item => ({
        run_id: item.run_id,
        asset_id: item.asset_id,
        status: "queued",
        snapshot_hash: "",
        revision: 1,
      }));
      setRuns(createdRuns);
      setSelected([]);
      window.setTimeout(() => void refreshRuns(createdRuns), 500);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}：${err.message}` : err instanceof Error ? err.message : "任务创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function resume(run: PipelineRun) {
    try {
      await api.resumeRun(ctx, run.run_id);
      await refreshRuns();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}：${err.message}` : "恢复被后端拒绝");
    }
  }

  function toggle(id: string) {
    setSelected(value => value.includes(id) ? value.filter(item => item !== id) : [...value, id]);
  }

  return (
    <Page title="数据处理中心" subtitle="HTTP 202 只表示已入队；算子版本和配置快照由服务端执行并持久化。">
      <div className="two-col">
        <Card title="流水线模板与算子">
          <div className="notice">
            <strong>可用算子</strong>
            {operators.map(operator => (
              <small key={operator.operator_key}>
                {operator.operator_key} · {operator.version} · {operator.available ? "可用" : operator.reason}
              </small>
            ))}
          </div>
          <div className="toolbar">
            <button className="button secondary" onClick={() => setSelected(selected.length === assets.length ? [] : assets.map(asset => asset.asset_id))}>
              {selected.length === assets.length ? "取消全选" : "全选资产"}
            </button>
            <span className="muted">已选 {selected.length} / {assets.length}</span>
          </div>
          <div className="select-list">
            {assets.map(asset => (
              <label key={asset.asset_id} className="check-row">
                <input type="checkbox" checked={selected.includes(asset.asset_id)} onChange={() => toggle(asset.asset_id)} />
                <span>{asset.filename}</span><small>{asset.format.toUpperCase()}</small>
              </label>
            ))}
            {!assets.length && <Empty>请先完成文件接入。</Empty>}
          </div>
          <Field label="算子参数 JSON（提交后形成不可变 Run 快照）">
            <label>解析器<select aria-label="解析器" value={parserKind} onChange={e=>setParserKind(e.target.value)}><option value="builtin">内置 PDF / HTML</option><option value="layout">原生 PDF 版面与坐标（启发式）</option><option value="ocr">英文扫描 PDF · 真实 OCR（最多 10 页）</option></select></label>
            <textarea value={config} onChange={event => setConfig(event.target.value)} rows={8} />
          </Field>
          {error && <ErrorBox message={error} />}
          <button className="button primary" disabled={busy || !selected.length} onClick={() => void create()}>
            {busy ? "提交中…" : "创建 N 个独立 Run"}
          </button>
        </Card>
        <Card title="Run、节点和产物">
          <div className="list">
            {runs.map(run => (
              <div className="run-card" key={run.run_id}>
                <div className="list-row">
                  <div><strong>{run.run_id.slice(0, 12)}</strong><small>Asset {run.asset_id.slice(0, 12)} · revision {run.revision}</small></div>
                  <span data-testid="run-status"><Badge value={run.status} /></span>
                </div>
                {run.error_code && <div className="bad-text">错误：{run.error_code}</div>}
                {run.nodes?.map(node => (
                  <div className="node-row" key={`${run.run_id}-${node.node_id}`}>
                    <span><strong>{node.node_id}</strong> · {node.operator_version ?? "—"}</span>
                    <small>{node.input_count} → {node.output_count}，过滤 {node.filtered_count}，{Math.round(node.duration_ms ?? 0)} ms</small>
                    <Badge value={node.status} />
                  </div>
                ))}
                {artifacts[run.run_id]?.map(artifact => <code className="log-line" key={artifact.artifact_id}>产物 {artifact.kind} · {artifact.sha256.slice(0, 12)}</code>)}
                <div className="toolbar">
                  <button className="button tiny" onClick={() => void refreshRuns()}>刷新</button>
                  {["failed", "ready_to_resume"].includes(run.status) && <button className="button tiny" onClick={() => void resume(run)}>恢复</button>}
                </div>
                {logs[run.run_id]?.map((line, index) => <code className="log-line" key={`${line}-${index}`}>{formatTime()} {line}</code>)}
              </div>
            ))}
            {!runs.length && <Empty>创建批次后将显示每个独立 Run、节点指标和真实产物。</Empty>}
          </div>
        </Card>
      </div>
    </Page>
  );
}
