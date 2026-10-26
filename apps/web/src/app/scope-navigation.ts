/** Catalog, processing and lineage share one immutable workspace snapshot. */
export function scopeDestination(path: string, _fromPath: string, current: URLSearchParams) {
  if (path.startsWith("/advanced/")) return path;
  const params = new URLSearchParams();
  const catalog = path === "/ingest" ? "workspace" : current.get("catalog") === "workspace" ? "workspace" : "generated";
  if (current.has("catalog") || path === "/ingest") params.set("catalog", catalog);
  const revision = current.get("revision");
  if (revision && (path !== "/ingest" || current.get("catalog") === "workspace")) params.set("revision", revision);
  return `${path}${params.size ? `?${params}` : ""}`;
}
