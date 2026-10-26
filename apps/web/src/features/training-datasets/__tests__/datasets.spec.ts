/// <reference types="node" />
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { DatasetOverviewResponse, DatasetsResponse, SamplesResponse, Scope, TrainingKind } from "../../../contracts/training-center";

const bundle = JSON.parse(readFileSync(new URL("../../../../../../contracts/training-center/examples.json", import.meta.url), "utf8"));
const cases = bundle.scenarios.success.responses;
const datasetOverview = (kind: TrainingKind) => cases[`${kind}_overview`].body as DatasetOverviewResponse;
const datasets = () => cases.datasets.body as DatasetsResponse;
const fixtureScope = () => cases.overview.body.scope as Scope;
const samples = () => [cases.cpt_samples, cases.cpt_samples_next, cases.sft_samples, cases.dpo_samples].flatMap(item => (item.body as SamplesResponse).items);

// Browser-only contract fixtures. Backend acceptance is covered by real SQLite/router tests.
const session = { token: "datasets-browser", user_id: "viewer", workspace_id: fixtureScope().workspace_id, role: "admin" };
async function open(page: Page, kind: TrainingKind, tab = "overview", role = "viewer") {
  await page.addInitScript(value => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), session);
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const memberships = [{ workspace_id: session.workspace_id, role }];
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: { user_id: session.user_id, workspaces: memberships } });
    if (url.pathname.endsWith("/workspaces")) return route.fulfill({ json: { items: memberships } });
    if (url.pathname.endsWith("/dataset-products/types")) return route.fulfill({ json: { items: [{ product_type: "pretrain", description: "CPT" }, { product_type: "sft", description: "SFT" }] } });
    if (url.pathname === "/api/v1/datasets") return route.fulfill({ json: { items: [{ dataset_id: "workspace-sft", name: "SFT", product_type: "sft" }, { dataset_id: "workspace-cpt", name: "CPT", product_type: "pretrain" }] } });
    if (url.pathname.endsWith("/training-center/datasets")) return route.fulfill({ json: { ...datasets(), items: datasets().items.filter(d => d.kind === kind) } });
    if (url.pathname.endsWith("/overview")) return route.fulfill({ json: datasetOverview(kind) });
    if (url.pathname.endsWith("/samples")) {
      const found = samples().filter(s => s.kind === kind);
      const selected = found.filter(s => (!url.searchParams.get("split") || s.split === url.searchParams.get("split")) && (!url.searchParams.get("q") || JSON.stringify(s).includes(url.searchParams.get("q")!)));
      const offset = Number(url.searchParams.get("offset") || 0);
      return route.fulfill({ json: { scope: fixtureScope(), items: selected.slice(offset, offset + 20), total_count: selected.length, offset, limit: 20 } });
    }
    return route.fulfill({ status: 503, json: { error: { code: "ADAPTER_UNAVAILABLE", message: "导出依赖尚未就绪" }, request_id: "browser-test" } });
  });
  await page.goto(`/#/datasets/${kind}?tab=${tab}`);
  await expect(page.getByRole("heading", { name: "训练数据集", exact: true })).toBeVisible();
}

test("overview pins revision, shows split units and preserves version through reload", async ({ page }) => {
  await open(page, "cpt");
  await expect(page).toHaveURL(/revision=/);
  await expect(page.getByRole("heading", { name: "数据划分" })).toBeVisible();
  const option = datasets().items.find(d => d.kind === "cpt")!;
  await page.getByLabel("数据集与版本").selectOption(option.version_id);
  await expect(page).toHaveURL(/dataset_id=/);
  await page.reload();
  await expect(page.getByLabel("数据集与版本")).toHaveValue(option.version_id);
  await expect(page.getByRole("button", { name: "构建 CPT" })).toHaveCount(0);
  await page.screenshot({ path: "../../.local/training-center/cpt-overview.png", fullPage: true });
});

test("CPT filters before paging and keeps URL search on reload", async ({ page }) => {
  await open(page, "cpt", "samples");
  await expect(page.getByText("共 23 篇")).toBeVisible();
  await page.getByTitle("2", { exact: true }).click();
  await expect(page).toHaveURL(/offset=20/);
  await page.getByLabel("样本划分").selectOption("test");
  await expect(page).not.toHaveURL(/offset=20/);
  await expect(page.getByText("共 1 篇")).toBeVisible();
  await page.getByLabel("搜索样本").fill("no-matching-text-123");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText("当前条件下没有样本。")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("搜索样本")).toHaveValue("no-matching-text-123");
});

test("SFT preserves role order and surfaces failed download", async ({ page }) => {
  await open(page, "sft", "samples");
  await expect(page.locator("li[data-role]").first()).toBeVisible();
  const sample = samples().find(s => s.kind === "sft")!;
  if (sample.kind !== "sft") throw new Error("fixture mismatch");
  expect(await page.locator("li[data-role]").evaluateAll(nodes => nodes.map(n => n.getAttribute("data-role")))).toEqual(sample.messages.map(m => m.role));
  await page.getByRole("button", { name: "导出数据" }).hover();
  await page.getByRole("menuitem", { name: "JSONL" }).click();
  await expect(page.getByText("导出依赖尚未就绪")).toBeVisible();
  await page.screenshot({ path: "../../.local/training-center/sft-samples.png", fullPage: true });
});

test("DPO displays both answers, no horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, "dpo", "samples");
  await expect(page.getByRole("heading", { name: "Chosen · 优选回答" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rejected · 非优选回答" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "../../.local/training-center/dpo-mobile.png", fullPage: true });
});

test("expired snapshot requires refresh and does not silently substitute fixtures", async ({ page }) => {
  await open(page, "cpt");
  await expect(page).toHaveURL(/revision=/);
  await page.route("**/api/v1/training-center/datasets?**", route => {
    const url = new URL(route.request().url());
    if (url.searchParams.has("revision")) return route.fulfill({ status: 409, json: { error: { code: "SNAPSHOT_EXPIRED", message: "快照已过期" } } });
    return route.fallback();
  });
  await page.reload();
  await expect(page.getByText("快照已过期")).toBeVisible();
  await expect(page.getByRole("heading", { name: "数据划分" })).toHaveCount(0);
  await page.unroute("**/api/v1/training-center/datasets?**");
  await page.getByRole("button", { name: "刷新快照" }).click();
  await expect(page.getByRole("heading", { name: "数据划分" })).toBeVisible();
});

test("CPT builder switches to workspace and defaults to pretrain with actual IDs", async ({ page }) => {
  await open(page, "cpt", "overview", "engineer");
  await page.getByRole("button", { name: "构建 CPT" }).click();
  await expect(page).toHaveURL(/catalog=workspace/);
  await expect(page.getByLabel("产品类型")).toHaveValue("pretrain");
  await expect(page.locator('select').filter({ has: page.locator('option[value="workspace-cpt"]') })).toHaveValue("workspace-cpt");
});
