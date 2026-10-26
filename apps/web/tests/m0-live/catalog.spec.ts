import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

interface CatalogContext {
  user_id: string; workspace_name: string; workspace_id: string; revision: string;
  file_count: number; record_count: number; first_file: { id: string; filename: string };
  source_counts: Record<string, number>;
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

test("real expired revision refreshes the whole page; workspace adapter failure stays visible", async ({ page }) => {
  const ctx = await login(page, `/data/txt?catalog=generated&revision=${"a".repeat(64)}&offset=20`);
  await expect(page.getByText("数据快照已过期", { exact: true })).toBeVisible();
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(0);
  await page.getByRole("button", { name: "刷新快照", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`revision=${ctx.revision}`));
  await expect(page).not.toHaveURL(/offset=/);
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(20);
  const unavailable = page.waitForResponse(response => response.url().includes("/training-center/files?") && new URL(response.url()).searchParams.get("catalog") === "workspace");
  await page.getByRole("radiogroup", { name: "数据目录" }).getByText("工作空间", { exact: true }).click();
  const response = await unavailable;
  expect(response.status()).toBe(503);
  expect((await response.json()).error.code).toBe("ADAPTER_UNAVAILABLE");
  await expect(page.getByRole("alert")).toContainText("当前数据适配器暂不可用");
  await expect(page.locator("tbody tr.ant-table-row")).toHaveCount(0);
});
