import { expect, test, type Page } from "@playwright/test";
import examples from "../../../../../contracts/training-center/examples.json" with { type: "json" };

const responses = examples.scenarios.success.responses;
const session = { token: "m1-browser-test", user_id: "m1-user", workspace_id: "m1-space", role: "admin" };
const revision = responses.overview.body.scope.revision;
const firstFile = responses.files.body.items[0];

// These are browser-test responses derived from the canonical contract bundle.
// They are never loaded by production code or enabled by a failed real request.
function scoped<T>(data: T, catalog = "generated", snapshot = revision): T {
  return JSON.parse(JSON.stringify(data), (key, value) => key === "workspace_id" ? session.workspace_id : key === "catalog" ? catalog : key === "revision" ? snapshot : key === "as_of" ? responses.overview.body.scope.as_of : value);
}
async function login(page: Page, path = "/home") {
  await page.addInitScript(value => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), session);
  await page.goto(`/#${path}`);
}
async function backend(page: Page, options: { expired?: boolean; workspaceComparison?: boolean; mismatch?: boolean; populatedCharts?: boolean; wrongAsOf?: boolean; wrongRun?: boolean; noEvidence?: boolean; denied?: boolean; empty?: boolean } = {}) {
  const requests: URL[] = [];
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    requests.push(url);
    const path = url.pathname.replace("/api/v1", "");
    if (path === "/auth/me") return route.fulfill({ json: { user_id: session.user_id, workspaces: [{ workspace_id: session.workspace_id, role: "admin" }] } });
    if (path === "/workspaces") return route.fulfill({ json: { items: [{ workspace_id: session.workspace_id, role: "admin" }] } });
    if (options.denied) return route.fulfill({ status: 403, json: { request_id: "permission-check", error: { code: "PERMISSION_DENIED", message: "没有访问当前工作空间或资源的权限", retryable: false } } });
    const catalog = url.searchParams.get("catalog") || "generated";
    const snapshot = url.searchParams.get("revision") || (options.expired ? "fresh-revision" : revision);
    if (catalog === "workspace" && !options.workspaceComparison) return route.fulfill({ status: 503, json: { error: { code: "M1_SERVICE_UNAVAILABLE", message: "工作空间接口不可用", retryable: false } } });
    if (path.endsWith("/stats") && options.expired && snapshot === "expired") return route.fulfill({ status: 409, json: { error: { code: "SNAPSHOT_EXPIRED", message: "快照已过期", retryable: false } } });
    if (path === "/training-center/overview") return route.fulfill({ json: scoped(options.empty ? examples.scenarios.empty.responses.overview.body : responses.overview.body, catalog, options.mismatch ? "wrong-revision" : snapshot) });
    if (path === "/training-center/datasets") return route.fulfill({ json: scoped(responses.datasets.body, catalog, snapshot) });
    if (path === "/training-center/files") {
      let items = scoped(responses.files.body.items, catalog, snapshot);
      const format = url.searchParams.get("format");
      const q = url.searchParams.get("q") || "";
      const source = url.searchParams.get("source_kind");
      items = items.filter(item => (!format || format === "all" || format === item.format) && item.filename.includes(q) && (!source || item.source_kind === source));
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 20);
      return route.fulfill({ json: { ...scoped(responses.files.body, catalog, snapshot), items: items.slice(offset, offset + limit), total_count: items.length, offset, limit } });
    }
    if (path.endsWith("/stats")) {
      const data = scoped(responses.txt_stats.body, catalog, snapshot);
      if (options.wrongAsOf) data.scope.as_of = "2026-10-27T01:00:00Z";
      if (path.includes("/pdf/")) data.metrics.file_count.value = 0;
      if (options.populatedCharts) {
        const points = Array.from({ length: 35 }, (_, index) => ({ date: new Date(Date.UTC(2026, 8, 23 + index)).toISOString().slice(0, 10), count: index % 5 }));
        return route.fulfill({ json: { ...data, availability: { ingestion_trend: "available" }, ingestion_trend: { timezone: "UTC", from: "2026-09-23T00:00:00Z", to: "2026-10-27T23:59:59Z", unit: "file", points }, length_distribution: { ...data.length_distribution, total_count: 8, buckets: [{ key: "0-127", label: "0-127", count: 8, ratio: 1 }] } } });
      }
      return route.fulfill({ json: data });
    }
    if (path === `/training-center/files/${firstFile.id}`) {
      const data = scoped(responses.file_detail.body, catalog, snapshot);
      return route.fulfill({ json: { ...data, processing_summary_ref: options.workspaceComparison && !options.noEvidence ? { catalog: "workspace", type: "pipeline_run", id: "m1-run" } : null } });
    }
    if (path === "/pipeline-runs/m1-run/summary") {
      const data = scoped(responses.processing_summary.body, catalog, snapshot);
      return route.fulfill({ json: { ...data, run_id: "m1-run", steps: data.steps.map(step => ({ ...step, run_id: "m1-run" })), input_refs: [{ catalog: "workspace", type: "file", id: options.wrongRun ? "unrelated-file" : firstFile.id }] } });
    }
    if (path === `/training-center/files/${firstFile.id}/comparison` && catalog === "workspace" && url.searchParams.has("record_id")) {
      const comparison = scoped(responses.comparison.body, catalog, snapshot);
      comparison.processing_run_ref.id = options.wrongRun ? "another-run" : "m1-run";
      comparison.before.text = '<img src=x onerror="window.m1Xss=true">';
      return route.fulfill({ json: comparison });
    }
    return route.fulfill({ status: 404, json: { error: { code: "COMPARISON_NOT_AVAILABLE", message: "无已有对比记录", retryable: false } } });
  });
  return requests;
}

test.describe("M1 real-client browser integration", () => {
  test.skip(process.env.M0_FIXTURES === "true", "Exercises HTTP client with fixtures explicitly disabled");

  test("home uses canonical metrics, version links and responsive format navigation", async ({ page }) => {
    await backend(page);
    await login(page);
    await expect(page).toHaveURL(new RegExp(`revision=${revision}`));
    await expect(page.getByRole("region", { name: "原始文件", exact: true })).toContainText("13");
    await expect(page.getByRole("region", { name: "训练记录", exact: true })).toContainText("41");
    await expect(page.getByRole("region", { name: "质量通过率", exact: true })).toContainText("暂无统计");
    await expect(page.locator("a[data-format]")).toHaveCount(8);
    for (const dataset of responses.datasets.body.items) {
      const link = page.locator(`a[href*="dataset_id=${dataset.id}"]`).first();
      await expect(link).toHaveAttribute("href", new RegExp(`version=${dataset.version}`));
    }
    await expect(page.getByText("暂无已记录的流转关联")).toBeVisible();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: test.info().outputPath("home-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: test.info().outputPath("home-mobile.png"), fullPage: true });
    await page.locator('a[data-format="txt"]').click();
    await expect(page.getByRole("heading", { name: "数据台", exact: true })).toBeVisible();
    await expect(page.getByRole("img", { name: "文件来源分布，总计 13 个文件" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: test.info().outputPath("explorer-mobile.png"), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: test.info().outputPath("explorer-desktop.png"), fullPage: true });
  });

  test("paging, search, format cache and detail deep links retain their scope", async ({ page }) => {
    const requests = await backend(page);
    await login(page, "/data/txt?limit=10");
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(10);
    await page.locator('.ant-pagination-item[title="2"]').click();
    await expect(page).toHaveURL(/offset=10/);
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(3);
    await page.getByRole("searchbox", { name: "搜索文件名" }).fill(firstFile.filename);
    await page.getByRole("searchbox", { name: "搜索文件名" }).press("Enter");
    await expect(page).not.toHaveURL(/offset=/);
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(1);
    await expect(page.getByRole("region", { name: "文件数量", exact: true })).toContainText("13");
    await page.getByRole("button", { name: `TXT ${firstFile.filename}` }).click();
    await expect(page).toHaveURL(new RegExp(`file_id=${firstFile.id}`));
    await expect(page.getByRole("dialog")).toContainText(responses.file_detail.body.source.name);
    await page.reload();
    await expect(page.getByRole("dialog")).toContainText(firstFile.id);
    await page.getByRole("tab", { name: "清洗前后对比" }).click();
    await expect(page.getByRole("dialog")).toContainText("暂无清洗对比");
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await page.getByRole("navigation", { name: "文件格式" }).getByRole("link", { name: "PDF", exact: true }).click();
    await expect(page.getByRole("region", { name: "文件数量", exact: true }).locator("strong")).toHaveText("0个文件");
    await page.getByRole("navigation", { name: "文件格式" }).getByRole("link", { name: "TXT", exact: true }).click();
    await expect(page.getByRole("region", { name: "文件数量", exact: true }).locator("strong")).toHaveText("13个文件");
    await page.getByRole("combobox", { name: "来源类别" }).click();
    await page.getByTitle("网页", { exact: true }).click();
    await expect(page).toHaveURL(/source_kind=web/);
    await expect.poll(() => requests.some(url => url.pathname.endsWith("/txt/stats") && url.searchParams.get("source_kind") === "web")).toBe(true);
    expect(requests.filter(url => url.pathname.endsWith("/stats")).every(url => url.searchParams.get("revision") === revision && !url.searchParams.has("q"))).toBe(true);
  });

  test("expired snapshots refresh every resource and catalog errors never use cached generated data", async ({ page }) => {
    const requests = await backend(page, { expired: true });
    await login(page, "/data/txt?catalog=generated&revision=expired&offset=10");
    await expect(page.getByText("数据快照已过期", { exact: true })).toBeVisible();
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(0);
    await page.getByRole("button", { name: "刷新快照", exact: true }).click();
    await expect(page).toHaveURL(/revision=fresh-revision/);
    await expect(page).not.toHaveURL(/offset=/);
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(13);
    await expect.poll(() => requests.some(url => url.pathname.endsWith("/txt/stats") && url.searchParams.get("revision") === "fresh-revision")).toBe(true);
    await page.getByRole("button", { name: "刷新数据快照" }).click();
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(13);
    await page.getByText("工作空间", { exact: true }).click();
    await expect(page.getByText("工作空间接口不可用", { exact: true })).toBeVisible();
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(0);
    await expect(page.getByText("正在加载…", { exact: true })).toHaveCount(0);
  });

  test("workspace comparison uses file-scoped mapping and escapes raw text", async ({ page }) => {
    const requests = await backend(page, { workspaceComparison: true });
    await login(page, `/data/txt?catalog=workspace&file_id=${firstFile.id}&detail_tab=comparison&record_id=m0-example-record`);
    await expect(page.getByRole("heading", { name: "处理前", exact: true })).toBeVisible();
    await expect(page.getByRole("dialog").locator("pre").first()).toHaveText('<img src=x onerror="window.m1Xss=true">');
    await expect(page.getByRole("dialog").locator("pre img")).toHaveCount(0);
    expect(requests.some(url => url.pathname.endsWith(`/files/${firstFile.id}/comparison`) && url.searchParams.get("record_id") === "m0-example-record")).toBe(true);
    expect(requests.some(url => url.pathname.includes("/pipeline-runs/"))).toBe(false);
    await expect(page.getByRole("link", { name: "查看记录血缘" })).toHaveAttribute("href", /root_type=segment.*root_id=m0-example-record/);
  });

  test("a response from another revision is rejected", async ({ page }) => {
    await backend(page, { mismatch: true });
    await login(page, `/home?catalog=generated&revision=${revision}`);
    await expect(page.getByRole("region", { name: "原始文件", exact: true })).toHaveCount(0);
    await expect(page.getByText(/响应范围/)).toBeVisible();
  });

  test("a multi-file workspace run never supplies an arbitrary comparison", async ({ page }) => {
    const requests = await backend(page, { workspaceComparison: true });
    await login(page, `/data/txt?catalog=workspace&file_id=${firstFile.id}&detail_tab=comparison`);
    await expect(page.getByRole("dialog")).toContainText("暂无清洗对比");
    expect(requests.some(url => url.pathname.includes("/pipeline-runs/"))).toBe(false);
  });

  test("same revision with different snapshot metadata cannot mix data", async ({ page }) => {
    await backend(page, { wrongAsOf: true, workspaceComparison: true });
    await login(page, "/data/txt?catalog=workspace");
    await expect(page.getByText("响应范围与当前快照不一致", { exact: true })).toBeVisible();
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "刷新快照", exact: true })).toBeVisible();
  });

  test("file summary is loaded only from its explicit run and survives refresh", async ({ page }) => {
    const requests = await backend(page, { workspaceComparison: true });
    await login(page, `/data/txt?catalog=workspace&file_id=${firstFile.id}&detail_tab=processing`);
    await expect(page.getByRole("dialog")).toContainText("character_normalize");
    await expect(page.getByRole("dialog")).toContainText("运行边界统计");
    await page.reload();
    await expect(page.getByRole("dialog")).toContainText("character_normalize");
    expect(requests.filter(url => url.pathname.endsWith("/summary")).every(url => url.pathname.endsWith("/m1-run/summary") && url.searchParams.get("revision") === revision)).toBe(true);
  });

  test("unrelated file/run responses are rejected for both summary and comparison", async ({ page }) => {
    await backend(page, { workspaceComparison: true, wrongRun: true });
    await login(page, `/data/txt?catalog=workspace&file_id=${firstFile.id}&detail_tab=processing&record_id=m0-example-record`);
    await expect(page.getByRole("dialog")).toContainText("处理摘要与当前文件的运行引用不一致");
    await expect(page.getByRole("dialog").getByText("character_normalize")).toHaveCount(0);
    await page.getByRole("tab", { name: "清洗前后对比" }).click();
    await expect(page.getByRole("dialog")).toContainText("返回的对比与当前文件的处理记录不一致");
    await expect(page.getByRole("dialog").locator("pre")).toHaveCount(0);
  });

  test("no processing evidence stays unavailable without looking up arbitrary runs", async ({ page }) => {
    const requests = await backend(page, { workspaceComparison: true, noEvidence: true });
    await login(page, `/data/txt?catalog=workspace&file_id=${firstFile.id}&detail_tab=processing`);
    await expect(page.getByRole("dialog")).toContainText("暂无可关联的处理记录");
    await page.getByRole("tab", { name: "清洗前后对比" }).click();
    await expect(page.getByRole("dialog")).toContainText("暂无清洗对比");
    expect(requests.some(url => url.pathname.includes("/pipeline-runs/") || url.pathname.endsWith("/comparison"))).toBe(false);
  });

  test("workspace permission errors and empty state are distinct and never fallback", async ({ page }) => {
    await backend(page, { denied: true });
    await login(page, "/home?catalog=workspace");
    await expect(page.getByText("没有访问权限", { exact: true })).toBeVisible();
    await expect(page.getByText("请求编号：permission-check")).toBeVisible();
    await expect(page.locator("a[data-format]")).toHaveCount(0);
    await page.unrouteAll();
    await backend(page, { workspaceComparison: true, empty: true });
    await page.reload();
    await expect(page.getByRole("region", { name: "原始文件", exact: true }).locator("strong")).toHaveText("0个文件");
    await expect(page.getByText("暂无活动记录", { exact: true })).toBeVisible();
  });

  test("independent workspace graph tokens are not reused by catalog navigation", async ({ page }) => {
    await backend(page, { workspaceComparison: true });
    await login(page, "/home?catalog=workspace");
    await expect(page).toHaveURL(new RegExp(`revision=${revision}`));
    await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "数据血缘", exact: true })).toHaveAttribute("href", "#/lineage?catalog=workspace&scope_reset=1");
    await page.goto("/#/lineage?catalog=workspace&revision=graph-only&root_type=file&root_id=file-a");
    const home = page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "首页", exact: true });
    await expect(home).toHaveAttribute("href", "#/home?catalog=workspace&scope_reset=1");
    await home.click();
    await expect(page.getByText("此页面将使用独立快照，请以本页统计时间为准。", { exact: true })).toBeVisible();
    await expect(page).not.toHaveURL(/graph-only/);
  });

  test("charts use whole-response counts and the last thirty UTC days", async ({ page }) => {
    await backend(page, { populatedCharts: true });
    await login(page, "/data/txt?limit=1");
    await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(1);
    await expect(page.getByRole("img", { name: "片段长度分布，总计 8 个片段" })).toBeVisible();
    await expect(page.getByRole("img", { name: "接入数量趋势", exact: true })).toBeVisible();
    await expect(page.getByText("2026-09-28 — 2026-10-27 · UTC", { exact: true })).toBeVisible();
  });
});

test("M1 explicit canonical fixture supports file details without fabricating comparison", async ({ page }) => {
  test.skip(process.env.M0_FIXTURES !== "true" || (process.env.M0_SCENARIO || "success") !== "success");
  await backend(page);
  await login(page, `/data/txt?file_id=${firstFile.id}&detail_tab=comparison`);
  await expect(page.getByRole("dialog")).toContainText("暂无清洗对比");
  await page.getByRole("tab", { name: "文件与来源" }).click();
  await expect(page.getByRole("dialog")).toContainText(responses.file_detail.body.source.name);
});
