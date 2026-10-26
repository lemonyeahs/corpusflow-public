/** acb7ce0 has independent graph snapshots. Remove this boundary only after shared-store acceptance. */
function domain(path: string) {
  if (path.startsWith("/lineage")) return "graph";
  if (path.startsWith("/ingest") || path.startsWith("/advanced/")) return "live";
  return "catalog";
}

export function scopeDestination(path: string, fromPath: string, current: URLSearchParams) {
  if (path.startsWith("/advanced/")) return path;
  if (path === "/ingest") return `${path}?catalog=workspace`;
  const params = new URLSearchParams();
  const catalog = current.get("catalog") === "workspace" ? "workspace" : "generated";
  if (current.has("catalog")) params.set("catalog", catalog);
  const revision = current.get("revision");
  if (revision) {
    if (catalog === "workspace" && domain(path) !== domain(fromPath)) params.set("scope_reset", "1");
    else params.set("revision", revision);
  }
  return `${path}${params.size ? `?${params}` : ""}`;
}
