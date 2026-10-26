import { cases, datasetOverview, datasets, errors, files, fixtureScope, graph, overview, samples, stats, type Scenario } from "./fixtures";
import { FORMATS, TRAINING_KINDS } from "../../contracts/training-center";

function scoped(value: unknown, workspace: string): unknown {
  if (Array.isArray(value)) return value.map(item => scoped(item, workspace));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, key === "workspace_id" ? workspace : scoped(item, workspace)]));
  return value;
}

/** Explicit development interception before network I/O; never a fallback after failure. */
export function fixtureResponse(path: string, headers: Headers, init: RequestInit): Response | undefined {
  const url = new URL(path, "http://fixture.invalid");
  const query = url.searchParams;
  if ((init.method || "GET").toUpperCase() !== "GET") return;
  const processing = /^\/pipeline-runs\/m0-example-run\/(summary|steps\/m0-example-step-1\/comparison)$/.test(url.pathname)
    && query.get("fixture") === "contract-v1";
  if (!processing && query.get("catalog") === "workspace") return;
  const datasetMatch = url.pathname.match(/^\/training-center\/datasets\/([^/]+)\/(overview|samples)$/);
  const supported = processing || datasetMatch || ["/training-center/overview", "/training-center/files", "/training-center/datasets", "/training-center/formats/txt/stats", "/lineage/graph"].includes(url.pathname);
  if (!supported) return;
  const mode = import.meta.env.VITE_TC_FIXTURE_SCENARIO || "success";
  if (!["success", "empty", "error"].includes(mode)) throw new Error("VITE_TC_FIXTURE_SCENARIO 必须是 success、empty 或 error");
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(scoped(body, headers.get("X-Workspace-ID") || "m0-example-workspace")), { status, headers: { "Content-Type": "application/json", "X-TC-Fixture": "contract-v1" } });
  const fail = (key: string) => json(errors[key].body, errors[key].status_code);
  if (mode === "error") return fail("unavailable");
  const scenario = mode as Scenario;
  const scope = fixtureScope(scenario);
  if (query.has("catalog") && !["generated", "workspace"].includes(query.get("catalog")!)) return fail("invalid_query");
  const expectedRevision = processing ? "m0-processing-example" : scope.revision;
  if (query.has("revision") && query.get("revision") !== expectedRevision) return fail("snapshot_expired");
  const allowed = new Set(["catalog", "revision"]);
  const allow = (...keys: string[]) => keys.forEach(key => allowed.add(key));
  if (processing) allow("fixture", "record_id");
  else if (url.pathname === "/training-center/files") allow("format", "q", "source_kind", "language", "status", "offset", "limit");
  else if (datasetMatch) allow("version", ...(datasetMatch[2] === "samples" ? ["q", "split", "offset", "limit"] : []));
  else if (url.pathname === "/training-center/datasets") allow("kind");
  else if (url.pathname.endsWith("/stats")) allow("timezone");
  else if (url.pathname === "/lineage/graph") allow("root_type", "root_id", "direction", "max_depth", "max_nodes");
  // Unrepresented filters must fail explicitly, rather than returning misleading full-cohort data.
  if ([...query.keys()].some(key => !allowed.has(key) || query.getAll(key).length !== 1)) return fail("invalid_query");
  if (processing) {
    if (query.has("catalog") && query.get("catalog") !== "workspace") return fail("invalid_query");
    if (query.has("record_id") && query.get("record_id") !== "m0-example-record") return fail("comparison_unavailable");
    const example = url.pathname.endsWith("/summary") ? cases(scenario).processing_summary : cases(scenario).comparison;
    return json(example.body, example.status_code);
  }
  if (url.pathname === "/training-center/overview") return json(overview(scenario));
  if (url.pathname.endsWith("/stats")) return query.has("timezone") && query.get("timezone") !== "UTC" ? fail("invalid_query") : json(stats(scenario));
  if (url.pathname === "/training-center/datasets") {
    const value = datasets(scenario);
    const kind = query.get("kind");
    if (kind && !TRAINING_KINDS.some(item => item === kind)) return fail("invalid_query");
    return json({ ...value, items: value.items.filter(item => !kind || item.kind === kind) });
  }
  if (url.pathname === "/lineage/graph") {
    const value = graph(scenario);
    if (!query.get("root_type") || !query.get("root_id")) return fail("invalid_query");
    if ((query.has("root_id") && query.get("root_id") !== value.root.id) || (query.has("root_type") && query.get("root_type") !== value.root.type)) return fail("not_found");
    const direction = query.get("direction") || "both";
    if (["max_depth", "max_nodes"].some(key => query.has(key) && !/^\d+$/.test(query.get(key)!))) return fail("invalid_query");
    const depth = Number(query.get("max_depth") ?? 6);
    const maxNodes = Number(query.get("max_nodes") ?? 200);
    if (!["both", "upstream", "downstream"].includes(direction) || !Number.isInteger(depth) || depth < 1 || depth > 12 || !Number.isInteger(maxNodes) || maxNodes < 1 || maxNodes > 500) return fail("invalid_query");
    if (direction === "downstream") return json({ ...value, nodes: value.nodes.filter(node => node.ref.id === value.root.id), edges: [] });
    if (maxNodes === 1 && value.nodes.length > 1) return json({ ...value, nodes: value.nodes.filter(node => node.ref.id === value.root.id), edges: [], truncated: true, truncation_reason: "max_nodes" });
    return json(value);
  }
  if (["offset", "limit"].some(key => query.has(key) && !/^\d+$/.test(query.get(key)!))) return fail("invalid_query");
  const offset = Number(query.get("offset") ?? 0);
  const limit = Number(query.get("limit") ?? 20);
  if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 100) return fail("invalid_query");
  const q = (query.get("q") || "").toLocaleLowerCase();
  let items: unknown[];
  if (!datasetMatch) {
    const format = query.get("format");
    const status = query.get("status");
    const source = query.get("source_kind");
    if ((format && !FORMATS.some(item => item === format)) || (status && !["unprocessed", "queued", "running", "succeeded", "partial", "failed"].includes(status)) || (source && !["web", "book", "paper", "other"].includes(source))) return fail("invalid_query");
    items = files(scenario).items.filter(item => (!format || format === "all" || item.format === format) && item.filename.toLocaleLowerCase().includes(q)
      && (!status || item.processing_status === status) && (!source || item.source_kind === source) && (!query.has("language") || item.language === query.get("language")));
  } else {
    if (!query.get("version")) return fail("invalid_query");
    let id: string;
    try { id = decodeURIComponent(datasetMatch[1]); } catch { return fail("invalid_query"); }
    const dataset = datasets(scenario).items.find(item => item.id === id);
    if (!dataset || (query.has("version") && query.get("version") !== dataset.version)) return fail("not_found");
    if (datasetMatch[2] === "overview") return json(datasetOverview(scenario, dataset.kind));
    const split = query.get("split");
    if (split && !["train", "validation", "test"].includes(split)) return fail("invalid_query");
    items = samples(scenario).filter(item => item.dataset_id === id && (!split || item.split === split)
      && (item.kind === "cpt" ? item.text : item.kind === "sft" ? item.messages.map(message => message.content).join("\n") : [item.prompt, item.chosen, item.rejected].join("\n")).toLocaleLowerCase().includes(q));
  }
  return json({ scope, items: items.slice(offset, offset + limit), total_count: items.length, offset, limit });
}
