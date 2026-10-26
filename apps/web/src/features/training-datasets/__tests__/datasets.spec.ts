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
    if (url.pathname.endsWith("/manifest")) return route.fulfill({ json: cases[`${kind}_manifest`].body });
    if (url.pathname.includes("/samples/")) {
      const sample = samples().find(s => s.kind === kind && s.id === decodeURIComponent(url.pathname.split("/").at(-1)!));
      return sample ? route.fulfill({ json: { scope: fixtureScope(), items: [sample], total_count: 1, offset: 0, limit: 1 } }) : route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND", message: "样本不存在" } } });
    }
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
  await page.getByRole("button", { name: "导出数据" }).click();
  const item = page.getByRole("menuitem", { name: "JSONL" });
  await item.focus();
  const [failed] = await Promise.all([page.waitForResponse(response => response.url().includes("/export?")), item.press("Enter")]);
  expect(failed.status()).toBe(503);
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

for (const field of ["as_of", "metric_definition_version"] as const) {
  test(`rejects changed ${field} within a cached revision and hides stale exports`, async ({ page }) => {
    await page.clock.install();
    await open(page, "cpt");
    await expect(page.getByRole("heading", { name: "数据划分" })).toBeVisible();
    await expect(page.getByRole("button", { name: "导出数据", exact: true })).toBeEnabled();
    const pinnedRevision = new URLSearchParams(new URL(page.url()).hash.split("?")[1]).get("revision");
    const pattern = "**/api/v1/training-center/datasets/*/overview?**";
    await page.route(pattern, route => {
      expect(new URL(route.request().url()).searchParams.get("revision")).toBe(pinnedRevision);
      const data = datasetOverview("cpt");
      return route.fulfill({ json: { ...data, scope: { ...data.scope, [field]: field === "as_of" ? "2099-01-01T00:00:00Z" : "unexpected-definition" } } });
    });
    await page.getByRole("button", { name: "样本浏览", exact: true }).click();
    await page.clock.fastForward(31_000);
    await page.getByRole("button", { name: "概览", exact: true }).click();
    await expect(page.getByText("响应范围与当前工作空间、目录或快照不一致，请刷新数据。", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "数据划分" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "数据集版本", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "导出数据", exact: true })).toHaveCount(0);
    await page.unroute(pattern);
    await page.getByRole("button", { name: /^重\s*试$/ }).click();
    await expect(page.getByRole("heading", { name: "数据划分" })).toBeVisible();
    await expect(page.getByRole("button", { name: "导出数据", exact: true })).toBeEnabled();
  });
}

test("expired refetch hides an already cached overview and its download action", async ({ page }) => {
  await page.clock.install();
  await open(page, "cpt");
  await expect(page.getByRole("heading", { name: "数据划分" })).toBeVisible();
  const pattern = "**/api/v1/training-center/datasets/*/overview?**";
  await page.route(pattern, route => route.fulfill({ status: 409, json: { error: { code: "SNAPSHOT_EXPIRED", message: "快照已过期" } } }));
  await page.getByRole("button", { name: "样本浏览", exact: true }).click();
  await page.clock.fastForward(31_000);
  await page.getByRole("button", { name: "概览", exact: true }).click();
  await expect(page.getByText("快照已过期", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "数据划分" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "导出数据", exact: true })).toHaveCount(0);
  await page.unroute(pattern);
  await page.getByRole("button", { name: "刷新快照", exact: true }).click();
  await expect(page.getByRole("heading", { name: "数据划分" })).toBeVisible();
});

test("CPT builder switches to workspace and defaults to pretrain with actual IDs", async ({ page }) => {
  await open(page, "cpt", "overview", "engineer");
  await page.getByRole("button", { name: "构建 CPT" }).click();
  await expect(page).toHaveURL(/catalog=workspace/);
  await expect(page.getByLabel("产品类型")).toHaveValue("pretrain");
  await expect(page.locator('select').filter({ has: page.locator('option[value="workspace-cpt"]') })).toHaveValue("workspace-cpt");
});

test("off-page sample deep link restores a version-scoped detail drawer", async ({ page }) => {
  await open(page, "cpt", "samples");
  await expect(page).toHaveURL(/revision=/);
  const sample = samples().filter(s => s.kind === "cpt").at(-1)!;
  await page.goto(page.url() + `&sample_id=${sample.id}`);
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText(sample.id);
  if (sample.kind === "cpt") await expect(page.getByRole("dialog")).toContainText(sample.text);
  await page.reload();
  await expect(page.getByRole("dialog")).toContainText(sample.id);
  await page.screenshot({ path: "../../.local/training-center/cpt-detail.png", fullPage: true });
});

test("manifest and empty versions are explicit", async ({ page }) => {
  await open(page, "sft", "manifest");
  await expect(page.getByText(`SHA-256：${cases.sft_manifest.body.content_hash}`)).toBeVisible();
  await expect(page.locator("pre")).toContainText("provenance");
  await page.route("**/api/v1/training-center/datasets?**", route => route.fulfill({ json: { scope: fixtureScope(), items: [] } }));
  await page.reload();
  await expect(page.getByText("此目录尚无已发布的数据集版本。")).toBeVisible();
  await expect(page.getByRole("button", { name: "导出数据" })).toHaveCount(0);
});

test("download sends all filters but never current page offset", async ({ page }) => {
  await open(page, "cpt", "samples");
  await page.getByLabel("样本划分").selectOption("train");
  await page.getByLabel("搜索样本").fill("第");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await page.getByTitle("2", { exact: true }).click();
  await expect(page).toHaveURL(/offset=20/);
  await page.route("**/api/v1/training-center/datasets/*/export?**", route => {
    const query = new URL(route.request().url()).searchParams;
    expect(query.get("q")).toBe("第"); expect(query.get("split")).toBe("train");
    expect(query.get("version")).toBeTruthy(); expect(query.get("revision")).toBeTruthy();
    expect(query.has("offset")).toBe(false); expect(query.has("limit")).toBe(false);
    return route.fulfill({ contentType: "application/x-ndjson; charset=utf-8", headers: { "Content-Disposition": "attachment; filename=records.jsonl" }, body: '{"text":"中文"}\n' });
  });
  await page.getByRole("button", { name: "导出数据" }).click();
  const [file] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: "JSONL" }).click()]);
  expect(file.suggestedFilename()).toBe("records.jsonl");
  expect(await file.failure()).toBeNull();
});

test("DPO embedded build keeps the existing validate and publish requests", async ({ page }) => {
  await open(page, "dpo", "overview", "engineer");
  const writes: string[] = [];
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/dpo/overview") return route.fulfill({ json: { total: 1, statuses: { approved: 1 }, published_count: 0 } });
    if (path === "/api/v1/dpo/preferences") return route.fulfill({ json: { items: [{ preference_sample_id: "real-pref", sample_key: "p1", prompt: "问题", response_a: "A", response_b: "B", evidence_ids: ["real-segment"], source_id: "real-source", status: "approved" }] } });
    if (path === "/api/v1/datasets") return route.fulfill({ json: { items: [{ dataset_id: "real-dpo", product_type: "dpo", name: "已授权 DPO" }] } });
    if (route.request().method() === "POST") {
      writes.push(path);
      if (path === "/api/v1/dpo/builds") {
        expect(route.request().postDataJSON().dataset_id).toBe("real-dpo");
        expect(route.request().postDataJSON().preference_sample_ids).toEqual(["real-pref"]);
        return route.fulfill({ json: { build_id: "real-build", candidate_count: 1 } });
      }
      if (path.endsWith("/validate")) return route.fulfill({ json: { ok: true } });
      if (path === "/api/v1/datasets/real-dpo/versions") return route.fulfill({ json: { dataset_version_id: "real-version" } });
    }
    return route.fallback();
  });
  await page.getByRole("button", { name: "构建 DPO", exact: true }).click();
  await page.getByRole("button", { name: "创建 DPO 构建", exact: true }).click();
  await page.getByRole("button", { name: "验证构建", exact: true }).click();
  await expect(page.getByText("构建快照验证通过。")).toBeVisible();
  await page.getByRole("button", { name: "发布不可变版本", exact: true }).click();
  await expect(page.getByText("DPO DatasetVersion real-version 已发布。")).toBeVisible();
  expect(writes).toEqual(["/api/v1/dpo/builds", "/api/v1/dataset-builds/real-build/validate", "/api/v1/datasets/real-dpo/versions"]);
});
