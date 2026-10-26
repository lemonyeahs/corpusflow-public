import { expect, test, type Page } from "@playwright/test";

const session = { token: "upstream-browser", user_id: "upstream-user", workspace_id: "upstream-space", role: "admin" };
const scope = { workspace_id: session.workspace_id, catalog: "workspace", revision: "run-revision", as_of: "2026-10-27T00:00:00Z", metric_definition_version: "1.0.0" };

async function login(page: Page, path: string) {
  await page.addInitScript(value => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), session);
  await page.goto(`/#${path}`);
}

test.describe("M1 upstream integration", () => {
  test.skip(process.env.M0_FIXTURES === "true", "Exercise HTTP handling with development fixtures disabled");

  test("reports failed ingestion setup requests without unhandled page errors", async ({ page }) => {
    const pageErrors: string[] = [];
    const failedRequests = new Set<string>();
    page.on("pageerror", error => pageErrors.push(error.message));
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/auth/me")) return route.fulfill({ json: { user_id: session.user_id } });
      if (path.endsWith("/workspaces")) return route.fulfill({ json: { items: [{ workspace_id: session.workspace_id, role: "admin" }] } });
      failedRequests.add(path);
      return route.fulfill({ status: 503, json: { error: { code: "SERVICE_UNAVAILABLE", message: "接入配置接口不可用" } } });
    });
    await login(page, "/ingest?catalog=workspace");
    await expect(page.getByText("接入配置接口不可用", { exact: true })).toBeVisible();
    await expect.poll(() => failedRequests.has("/api/v1/sources") && failedRequests.has("/api/v1/processing/operators")).toBe(true);
    await page.getByRole("button", { name: /^重\s*试$/ }).click();
    await expect(page.getByText("接入配置接口不可用", { exact: true })).toBeVisible();
    expect(pageErrors).toEqual([]);
  });

  test("keeps every selected file, polls all accepted runs, exposes errors and exports the selected run", async ({ page }) => {
    const reads: string[] = [];
    let uploadNumber = 0;
    let summaryUnavailable = true;
    let exportedPath = "";
    await page.route("**/api/v1/**", async route => {
      const url = new URL(route.request().url());
      const path = url.pathname.replace("/api/v1", "");
      if (path === "/auth/me") return route.fulfill({ json: { user_id: session.user_id } });
      if (path === "/workspaces") return route.fulfill({ json: { items: [{ workspace_id: session.workspace_id, role: "admin" }] } });
      if (path === "/processing/operators") return route.fulfill({ json: { items: [] } });
      if (path === "/sources") return route.fulfill({ json: route.request().method() === "POST" ? { source_id: "source-1", name: "测试来源", kind: "other" } : { items: [] } });
      if (path === "/uploads/init") return route.fulfill({ json: { upload_id: `upload-${++uploadNumber}` } });
      if (path.startsWith("/uploads/")) return route.fulfill({ json: { sha256: "test-checksum" } });
      if (path === "/ingest-batches") return route.fulfill({ json: { items: [1, 2, 3].map(id => ({ upload_id: `upload-${id}`, asset_id: `asset-${id}`, status: "registered" })) } });
      if (path === "/pipeline-runs/batches") return route.fulfill({ json: { accepted: [1, 2].map(id => ({ asset_id: `asset-${id}`, run_id: `run-${id}` })), rejected: [{ asset_id: "asset-3", reason: "测试拒绝原因" }] } });
      if (/^\/pipeline-runs\/run-\d$/.test(path)) {
        reads.push(path);
        return route.fulfill({ json: { run_id: path.split("/").at(-1), status: "succeeded" } });
      }
      if (path.endsWith("/summary")) {
        if (summaryUnavailable) return route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND", message: "处理摘要接口尚未注册" } } });
        return route.fulfill({ json: { scope, run_id: path.split("/")[2], status: "succeeded", input_refs: [], output_refs: [], steps: [], totals: [{ unit: "file", input_count: 1, output_count: 1 }, { unit: "segment", input_count: 2, output_count: 2 }] } });
      }
      if (path.endsWith("/export")) {
        exportedPath = path;
        return route.fulfill({ contentType: "application/x-ndjson", headers: { "Content-Disposition": "attachment; filename=selected-run.jsonl" }, body: '{"text":"selected run"}\n' });
      }
      return route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND" } } });
    });
    await login(page, "/ingest?catalog=workspace");
    await page.locator(".ant-upload input[type=file]").setInputFiles([1, 2, 3].map(id => ({ name: `file-${id}.txt`, mimeType: "text/plain", buffer: Buffer.from(`file ${id}`) })));
    for (const id of [1, 2, 3]) await expect(page.getByText(`file-${id}.txt`, { exact: true })).toBeVisible();
    await page.getByPlaceholder("可选", { exact: true }).fill("测试来源");
    await page.getByRole("button", { name: "开始处理", exact: true }).click();
    await expect.poll(() => uploadNumber).toBe(3);
    await expect.poll(() => reads.includes("/pipeline-runs/run-1") && reads.includes("/pipeline-runs/run-2")).toBe(true);
    await expect(page.getByText("已完成", { exact: true })).toHaveCount(2);
    await expect(page.getByText("测试拒绝原因", { exact: true })).toBeVisible();
    await expect(page.getByText("处理摘要接口尚未注册", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "导出数据" })).toBeDisabled();
    summaryUnavailable = false;
    await page.getByRole("button", { name: "刷新状态" }).click();
    await expect(page.getByText("导出范围：当前运行（单文件）", { exact: true })).toBeVisible();
    await page.getByLabel("当前运行", { exact: true }).selectOption("run-2");
    await expect(page.getByRole("button", { name: "导出数据" })).toBeEnabled();
    await page.getByRole("button", { name: "导出数据" }).click();
    const downloaded = page.waitForEvent("download");
    await page.getByRole("menuitem", { name: "JSONL", exact: true }).click();
    expect((await downloaded).suggestedFilename()).toBe("selected-run.jsonl");
    expect(exportedPath).toBe("/pipeline-runs/run-2/export");
  });

  test("pins the first graph revision before querying another direction", async ({ page }) => {
    const graphQueries: URL[] = [];
    await page.route("**/api/v1/**", async route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: { user_id: session.user_id } });
      if (url.pathname.endsWith("/workspaces")) return route.fulfill({ json: { items: [{ workspace_id: session.workspace_id, role: "admin" }] } });
      graphQueries.push(url);
      return route.fulfill({ json: { scope, root: { catalog: "workspace", type: "file", id: "file-1" }, nodes: [], edges: [], truncated: false, truncation_reason: null } });
    });
    await login(page, "/lineage?catalog=workspace&root_type=file&root_id=file-1");
    await expect(page).toHaveURL(/revision=run-revision/);
    await page.getByRole("combobox", { name: "方向", exact: true }).selectOption("upstream");
    await expect.poll(() => graphQueries.some(url => url.searchParams.get("direction") === "upstream" && url.searchParams.get("revision") === "run-revision")).toBe(true);
  });

  for (const catalog of ["workspace", "generated"] as const) {
  test(`${catalog} graph links preserve only compatible snapshots and open sample details`, async ({ page }) => {
    const nodes = [
      ["file", "file-1", "文件节点"],
      ["sample", "sample-1", "样本节点"],
      ["dataset_version", "dataset-v1", "数据集版本节点"],
      ["source", "source-1", "来源节点"],
      ["segment", "segment-1", "片段节点"],
      ...(catalog === "workspace" ? [["operator_run", "step-1", "处理记录节点"]] : []),
    ].map(([kind, id, label]) => ({
      id: `${catalog}:${kind}:${id}`,
      ref: { catalog, type: kind, id },
      kind,
      label,
      description: `${label}说明`,
      status: null,
      metrics: {},
      detail: kind === "sample"
        ? { dataset_id: "dataset-1", dataset_version: "1.0.0", dataset_kind: "sft" }
        : kind === "dataset_version"
          ? { dataset_id: "dataset-1", dataset_version: "1.0.0", dataset_kind: "sft" }
          : kind === "operator_run" ? { run_id: "actual-parent-run" } : {},
    }));
    await page.route("**/api/v1/**", async route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: { user_id: session.user_id } });
      if (url.pathname.endsWith("/workspaces")) return route.fulfill({ json: { items: [{ workspace_id: session.workspace_id, role: "admin" }] } });
      return route.fulfill({
        json: {
          scope: { ...scope, catalog },
          root: { catalog, type: "file", id: "file-1" },
          nodes,
          edges: [],
          truncated: false,
          truncation_reason: null,
        },
      });
    });
    await login(page, `/lineage?catalog=${catalog}&root_type=file&root_id=file-1`);
    await expect(page.getByText(`图 · ${nodes.length} 个节点 / 0 条边`, { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/revision=run-revision/);
    for (const [kind, id, label, target] of [
      ["file", "file-1", "文件节点", "/data/all"],
      ["sample", "sample-1", "样本节点", "/datasets/sft"],
      ["dataset_version", "dataset-v1", "数据集版本节点", "/datasets/sft"],
    ]) {
      await page.getByText(label, { exact: true }).click();
      const link = page.getByRole("link", { name: `打开${kind === "file" ? "文件" : kind === "sample" ? "样本" : "数据集版本"}` });
      await expect(link).toHaveAttribute("href", new RegExp(`${target}.*${kind === "file" ? `file_id=${id}` : kind === "sample" ? `sample_id=${id}` : "version=1.0.0"}`));
      const query = new URLSearchParams((await link.getAttribute("href"))!.split("?")[1]);
      expect(query.get("catalog")).toBe(catalog);
      expect(query.get("revision")).toBe(catalog === "generated" ? "run-revision" : null);
      expect(query.get("scope_reset")).toBe(catalog === "workspace" ? "1" : null);
      if (kind === "sample") expect(query.get("tab")).toBe("samples");
    }
    for (const [kind, id, label] of [["source", "source-1", "来源"], ["segment", "segment-1", "片段"]]) {
      await page.getByText(`${label}节点`, { exact: true }).click();
      const link = page.getByRole("link", { name: `打开${label}` });
      const query = new URLSearchParams((await link.getAttribute("href"))!.split("?")[1]);
      expect(query.get("root_type")).toBe(kind);
      expect(query.get("root_id")).toBe(id);
      expect(query.get("catalog")).toBe(catalog);
      expect(query.get("revision")).toBe("run-revision");
      expect(query.has("scope_reset")).toBe(false);
    }
    if (catalog === "workspace") {
      await page.getByText("处理记录节点", { exact: true }).click();
      await expect(page.getByRole("link", { name: "打开处理工具" })).toHaveAttribute("href", "#/advanced/processing");
      await expect(page.getByRole("link", { name: "打开处理记录" })).toHaveCount(0);
    }
  });
  }

  for (const mismatch of ["workspace_id", "catalog", "revision"] as const) {
    test(`lineage rejects ${mismatch} mismatch and clears root/revision when changing catalog`, async ({ page }) => {
      await page.route("**/api/v1/**", async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/auth/me")) return route.fulfill({ json: { user_id: session.user_id } });
        if (path.endsWith("/workspaces")) return route.fulfill({ json: { items: [{ workspace_id: session.workspace_id, role: "admin" }] } });
        return route.fulfill({ json: { scope: { ...scope, [mismatch]: "wrong-scope" }, root: { catalog: "workspace", type: "file", id: "file-1" }, nodes: [], edges: [], truncated: false, truncation_reason: null } });
      });
      await login(page, "/lineage?catalog=workspace&revision=run-revision&root_type=file&root_id=file-1");
      await expect(page.getByText(/SCOPE_MISMATCH/)).toBeVisible();
      await expect(page.getByText("图 · 0 个节点 / 0 条边", { exact: true })).toHaveCount(0);
      await page.getByRole("combobox", { name: "目录", exact: true }).selectOption("generated");
      await expect(page.getByPlaceholder("输入真实对象 ID")).toHaveValue("");
      const params = new URLSearchParams(new URL(page.url()).hash.split("?")[1]);
      expect(params.get("catalog")).toBe("generated");
      expect(params.has("revision")).toBe(false);
      expect(params.has("root_id")).toBe(false);
      expect(params.has("root_type")).toBe(false);
    });
  }
});
