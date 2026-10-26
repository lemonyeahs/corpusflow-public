import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

interface CatalogContext {
  user_id: string; workspace_name: string; workspace_id: string; revision: string;
  file_count: number; record_count: number; first_file: { id: string; filename: string };
  source_counts: Record<string, number>;
  graph_root_id: string; graph_revision: string; generated_graph_root_id: string; generated_graph_revision: string;
  generated_sample_id: string;
  workspace_catalog: {
    scope: { revision: string };
    datasets: { id: string; kind: string; version: string; sample_ids: string[] }[];
  };
}
const contextPath = process.env.M1_CATALOG_CONTEXT;
const catalog: CatalogContext | null = contextPath ? JSON.parse(readFileSync(contextPath, "utf-8")) : null;
test.skip(!catalog, "Requires the disposable --catalog verification harness");
test.setTimeout(90_000);

async function login(page: Page, path = "/home?catalog=generated") {
  if (!catalog) throw new Error("Missing isolated catalog context");
  await page.goto(`/#${path}`);
  await page.getByLabel("开发身份标识").fill(catalog.user_id);
  await page.getByLabel("显示名称").fill("M1 真实目录验收");
  await page.getByLabel("工作空间", { exact: true }).fill(catalog.workspace_name);
  await page.getByRole("button", { name: "进入工作台" }).click();
  return catalog;
}

test("real 4300-record catalog drives home, filtered paging, file detail and comparison", async ({ page }) => {
  const errors: string[] = [];
  const requests: URL[] = [];
  const fixtureHeaders: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.url().includes("/training-center/")) requests.push(new URL(request.url())); });
  page.on("response", response => { if (response.headers()["x-tc-fixture"]) fixtureHeaders.push(response.url()); });
  const ctx = await login(page);
  await expect(page).toHaveURL(new RegExp(`revision=${ctx.revision}`));
  await expect(page.getByRole("region", { name: "原始文件", exact: true })).toContainText("860");
  await expect(page.getByRole("region", { name: "训练记录", exact: true })).toContainText("4,300");
  await expect(page.getByRole("region", { name: "质量通过率", exact: true })).toContainText("暂无统计");
  await page.screenshot({ path: test.info().outputPath("real-home-desktop.png"), fullPage: true });
  await page.locator('a[data-format="txt"]').click();
  await expect(page.getByRole("region", { name: "文件数量", exact: true })).toContainText("860");
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(20);
  await page.locator('.ant-pagination-item[title="2"]').click();
  await expect(page).toHaveURL(/offset=20/);
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(20);
  await page.getByRole("searchbox", { name: "搜索文件名" }).fill(ctx.first_file.filename);
  await page.getByRole("searchbox", { name: "搜索文件名" }).press("Enter");
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(1);
  await expect(page.getByRole("region", { name: "文件数量", exact: true })).toContainText("860");
  await page.getByRole("button", { name: `TXT ${ctx.first_file.filename}` }).click();
  await expect(page.getByRole("dialog")).toContainText(ctx.first_file.id);
  await page.reload();
  await expect(page.getByRole("dialog")).toContainText(ctx.first_file.id);
  await page.getByRole("tab", { name: "清洗前后对比" }).click();
  await expect(page.getByRole("dialog")).toContainText("暂无清洗对比");
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "清除筛选", exact: true }).click();
  await page.getByRole("combobox", { name: "来源类别" }).click();
  await page.getByTitle("网页", { exact: true }).click();
  await expect(page).toHaveURL(/source_kind=web/);
  await expect(page.getByRole("region", { name: "文件数量", exact: true }).locator("strong")).toHaveText(`${ctx.source_counts.web}个文件`);
  await expect(page.getByText(`共 ${ctx.source_counts.web} 个文件`, { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: `文件来源分布，总计 ${ctx.source_counts.web} 个文件` })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("real-explorer-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("real-explorer-mobile.png"), fullPage: true });
  expect(requests.some(url => url.pathname.endsWith("/files") && url.searchParams.get("offset") === "20")).toBe(true);
  expect(requests.filter(url => url.pathname.endsWith("/stats")).every(url => url.searchParams.get("revision") === ctx.revision && !url.searchParams.has("q"))).toBe(true);
  expect(fixtureHeaders).toEqual([]);
  expect(errors).toEqual([]);
});

test("real expired revision refreshes the whole page; workspace catalog stays isolated", async ({ page }) => {
  const ctx = await login(page, `/data/txt?catalog=generated&revision=${"a".repeat(64)}&offset=20`);
  await expect(page.getByText("数据快照已过期", { exact: true })).toBeVisible();
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(0);
  await page.getByRole("button", { name: "刷新快照", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`revision=${ctx.revision}`));
  await expect(page).not.toHaveURL(/offset=/);
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(20);
  const workspaceFiles = page.waitForResponse(response => response.url().includes("/training-center/files?") && new URL(response.url()).searchParams.get("catalog") === "workspace");
  await page.getByRole("radiogroup", { name: "数据目录" }).getByText("工作空间", { exact: true }).click();
  const response = await workspaceFiles;
  expect(response.status()).toBe(200);
  expect((await response.json()).scope.catalog).toBe("workspace");
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(1);
  await expect(page).not.toHaveURL(new RegExp(`revision=${ctx.revision}`));
  await expect(page.getByRole("region", { name: "文件数量", exact: true })).toContainText("1");
});

test("real workspace graph preserves its database snapshot and isolates catalog switching", async ({ page }) => {
  if (!catalog) throw new Error("Missing isolated catalog context");
  const ctx = await login(page, `/lineage?catalog=workspace&root_type=source&root_id=${catalog.graph_root_id}&revision=${catalog.graph_revision}`);
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await page.getByRole("combobox", { name: "方向", exact: true }).selectOption("downstream");
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await expect(page).toHaveURL(new RegExp(`revision=${ctx.graph_revision}`));
  await page.reload();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await page.screenshot({ path: test.info().outputPath("real-lineage-desktop.png"), fullPage: true });
  await page.getByRole("combobox", { name: "目录", exact: true }).selectOption("generated");
  await expect(page).not.toHaveURL(/revision=|root_id=|root_type=/);
  await expect(page.locator(".react-flow__node")).toHaveCount(0);
  await page.goto(`/#/lineage?catalog=generated&root_type=source&root_id=${ctx.graph_root_id}`);
  await expect(page.getByRole("alert")).toContainText("NOT_FOUND");
});

test("real generated graph renders published source and file nodes", async ({ page }) => {
  if (!catalog) throw new Error("Missing isolated catalog context");
  const ctx = await login(page, `/lineage?catalog=generated&root_type=source&root_id=${catalog.generated_graph_root_id}&revision=${catalog.generated_graph_revision}&max_nodes=5`);
  await expect(page.locator(".react-flow__node")).toHaveCount(5);
  await expect(page.getByText(/图 · 5 个节点/)).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`revision=${ctx.generated_graph_revision}`));
  await expect(page.locator(".react-flow__node").filter({ hasText: /file ·/ }).first()).toBeVisible();
  await page.goto(`/#/lineage?catalog=generated&root_type=sample&root_id=${ctx.generated_sample_id}&revision=${ctx.generated_graph_revision}&direction=downstream&max_depth=1`);
  await expect(page.locator('.react-flow__node [data-kind="dataset_version"]')).toHaveCount(1);
  await page.locator('.react-flow__node [data-kind="sample"]').click();
  await page.getByRole("link", { name: "打开样本 ↗", exact: true }).click();
  await expect(page).toHaveURL(/tab=samples/);
  await expect(page).toHaveURL(new RegExp(`revision=${ctx.generated_graph_revision}`));
  await expect(page.getByRole("dialog")).toContainText(ctx.generated_sample_id);
});

for (const kind of ["cpt", "sft", "dpo"]) {
  test(`real workspace ${kind} samples, manifest and filtered download`, async ({ page }) => {
    if (!catalog) throw new Error("Missing isolated catalog context");
    const entry = catalog.workspace_catalog.datasets.find(dataset => dataset.kind === kind)!;
    const query = new URLSearchParams({ catalog: "workspace", revision: catalog.workspace_catalog.scope.revision, dataset_id: entry.id, version: entry.version, tab: "samples" });
    await login(page, `/datasets/${kind}?${query}`);
    await expect(page.locator("main article")).toHaveCount(2);
    await page.getByRole("button", { name: /^#/ }).first().click();
    await expect(page.getByRole("dialog")).toContainText("测试筛选");
    const sourceLink = page.getByRole("dialog").locator('a[href*="lineage"]');
    await expect(sourceLink).toHaveAttribute("href", /scope_reset=1/);
    expect(await sourceLink.getAttribute("href")).not.toContain("revision=");
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await page.getByRole("textbox", { name: "搜索样本" }).fill("测试筛选");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(page).toHaveURL(/q=/);
    await expect(page.locator("main article")).toHaveCount(2);
    await page.getByRole("button", { name: "导出数据" }).click();
    const [file] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: "JSONL" }).click()]);
    expect(file.suggestedFilename()).toMatch(/\.jsonl$/);
    const records = readFileSync((await file.path())!, "utf-8").trim().split("\n").map(line => JSON.parse(line));
    expect(records.map(record => record.id).sort()).toEqual([...entry.sample_ids].sort());
    await page.getByRole("button", { name: "版本清单", exact: true }).click();
    await expect(page.locator("main pre")).toContainText("training-center.isolated-acceptance.v1");
    await expect(page.locator("main pre")).toContainText("no Worker or publish gate executed");
    await expect(page.getByRole("menuitem", { name: "JSONL" })).not.toBeVisible();
    if (kind === "dpo") {
      await page.setViewportSize({ width: 390, height: 844 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    }
    await page.screenshot({ path: test.info().outputPath(`real-${kind}-manifest.png`), fullPage: true });
  });
}
