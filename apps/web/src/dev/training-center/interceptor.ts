import { files, fixtureScope, graph, overview, sampleExamples } from "./fixtures";

/** Called before network I/O, never from a catch block. Auth and writes are never intercepted. */
export function fixtureResponse(path: string, headers: Headers, init: RequestInit): Response | undefined {
  const url = new URL(path, "http://fixture.invalid");
  if ((init.method || "GET").toUpperCase() !== "GET" || url.searchParams.get("catalog") === "workspace") return;
  const supported = url.pathname === "/training-center/overview" || url.pathname === "/training-center/files"
    || /^\/training-center\/datasets\/[^/]+\/samples$/.test(url.pathname) || url.pathname === "/lineage/graph";
  if (!supported) return;
  const scenario = import.meta.env.VITE_TC_FIXTURE_SCENARIO || "success";
  if (!["success", "empty", "error"].includes(scenario)) throw new Error("VITE_TC_FIXTURE_SCENARIO 必须是 success、empty 或 error");
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "X-TC-Fixture": "m0-fixture-v1" } });
  if (scenario === "error") return json({ error: { code: "FIXTURE_UNAVAILABLE", message: "显式选择的开发错误样例", retryable: false } }, 503);
  if (url.searchParams.has("revision") && url.searchParams.get("revision") !== fixtureScope.revision) return json({ error: { code: "SNAPSHOT_EXPIRED", message: "样例快照已过期", retryable: false } }, 409);
  const scope = { ...fixtureScope, workspace_id: headers.get("X-Workspace-ID") || "fixture-workspace" };
  const empty = scenario === "empty";
  if (url.pathname === "/training-center/overview") return json({ ...overview, scope, metrics: empty ? {} : overview.metrics });
  if (url.pathname === "/lineage/graph") {
    const root = { ...graph.root, type: url.searchParams.get("root_type") || graph.root.type, id: url.searchParams.get("root_id") || graph.root.id };
    if (root.id !== graph.root.id || root.type !== graph.root.type) return json({ error: { code: "NOT_FOUND", message: "此对象没有开发样例", retryable: false } }, 404);
    return json({ ...graph, scope, nodes: empty ? [] : graph.nodes });
  }
  const offset = Number(url.searchParams.get("offset") || 0);
  const limit = Number(url.searchParams.get("limit") || 20);
  if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 100) return json({ error: { code: "VALIDATION_ERROR", message: "分页参数无效", retryable: false } }, 422);
  let items: unknown[] = url.pathname === "/training-center/files" ? files.items : sampleExamples;
  if (url.pathname === "/training-center/files") {
    const format = url.searchParams.get("format");
    const q = url.searchParams.get("q");
    items = files.items.filter(item => (!format || format === "all" || item.format === format) && (!q || item.filename.includes(q))
      && (!url.searchParams.has("status") || item.processing_status === url.searchParams.get("status"))
      && (!url.searchParams.has("source_kind") || item.source_kind === url.searchParams.get("source_kind")));
  } else {
    const datasetId = decodeURIComponent(url.pathname.split("/")[3]);
    if (!sampleExamples.some(item => item.dataset_id === datasetId) || (url.searchParams.has("version") && url.searchParams.get("version") !== "v1")) return json({ error: { code: "NOT_FOUND", message: "此数据集版本没有开发样例" } }, 404);
    items = sampleExamples.filter(item => item.dataset_id === datasetId && (!url.searchParams.has("split") || item.split === url.searchParams.get("split")));
  }
  if (empty) items = [];
  return json({ scope, items: items.slice(offset, offset + limit), total_count: items.length, offset, limit });
}
