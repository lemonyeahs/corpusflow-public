import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const path = process.env.TC_FULL_CONTEXT;
const context = path ? JSON.parse(readFileSync(path, "utf-8")) : null;
test.skip(!context, "Requires verify_training_center_m0.py --full");
test.setTimeout(90_000);

test("desktop real processing, comparison and graph retain one workspace snapshot", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const scope = `catalog=workspace&revision=${context.scope.revision}`;
  await page.goto(`/#/ingest?${scope}&run_id=${context.run_id}`);
  await page.getByLabel("开发身份标识").fill(context.user_id);
  await page.getByLabel("显示名称").fill("完整真实流程验收");
  await page.getByLabel("工作空间", { exact: true }).fill(context.workspace_name);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByText("1. builtin.text", { exact: true })).toBeVisible();
  await expect(page.getByText("2. builtin.clean", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "导出数据" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.getByRole("menuitem", { name: "JSONL" }).click(),
  ]);
  expect(readFileSync((await download.path())!, "utf-8")).toContain("训练");
  await page.getByRole("link", { name: "查看文件与清洗对比" }).click();
  await expect(page.getByRole("dialog")).toContainText(context.asset_id);
  await page.getByRole("tab", { name: "清洗前后对比" }).click();
  await expect(page.getByRole("dialog")).toContainText("训练  数据");
  await expect(page.getByRole("dialog")).toContainText("训练 数据");
  await page.screenshot({ path: test.info().outputPath("real-comparison-desktop.png"), fullPage: true });
  await page.goto(`/#/lineage?${scope}&root_type=file&root_id=${context.asset_id}&direction=downstream&max_depth=6`);
  await expect(page.locator('.react-flow__node [data-kind="operator_run"]').first()).toBeVisible();
  await page.locator('.react-flow__node [data-kind="operator_run"]').filter({ hasText: "builtin.clean" }).click();
  await page.getByRole("link", { name: "打开处理运行 ↗", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`revision=${context.scope.revision}`));
  await expect(page).toHaveURL(new RegExp(`run_id=${context.run_id}`));
  await expect(page.getByText("2. builtin.clean", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("desktop real published CPT SFT DPO pages and manifests", async ({ page }) => {
  await page.goto(`/#/home?catalog=workspace&revision=${context.scope.revision}`);
  await page.getByLabel("开发身份标识").fill(context.user_id);
  await page.getByLabel("显示名称").fill("完整真实流程验收");
  await page.getByLabel("工作空间", { exact: true }).fill(context.workspace_name);
  await page.getByRole("button", { name: "进入工作台" }).click();
  for (const dataset of context.datasets) {
    const query = new URLSearchParams({ catalog: "workspace", revision: context.scope.revision, dataset_id: dataset.id, version: dataset.version, tab: "samples" });
    await page.goto(`/#/datasets/${dataset.kind}?${query}`);
    await expect(page.locator("main article").first()).toBeVisible();
    await page.getByRole("button", { name: "版本清单", exact: true }).click();
    await expect(page.locator("main pre")).toContainText(dataset.id);
    await page.screenshot({ path: test.info().outputPath(`published-${dataset.kind}-desktop.png`), fullPage: true });
  }
});

test("independent reviewer opens an existing build and explicitly verifies source text", async ({ page, request }) => {
  const response = await request.post("/api/v1/auth/session", { data: {
    user_id: "full-reviewer", display_name: "独立验收审核员", workspace_name: "Full reviewer",
  } });
  expect(response.status()).toBe(200);
  const session = { ...await response.json(), workspace_id: context.workspace_id };
  await page.goto("/");
  await page.evaluate(value => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), session);
  await page.goto("/#/advanced/datasets");
  await page.reload();
  await page.getByLabel("已有 Build ID").fill(context.review_build_id);
  await page.getByRole("button", { name: "加载待审构建" }).click();
  await page.getByRole("button", { name: /^读取来源片段/ }).click();
  await expect(page.locator("main details").first()).toContainText(context.review_evidence_text);
  await page.getByRole("checkbox", { name: "我已核对上述来源片段，审核通过时一并确认来源质量" }).check();
  const reviewed = page.waitForResponse(result => result.url().includes("/candidate-samples/") && result.url().endsWith("/reviews"));
  await page.getByRole("button", { name: "通过", exact: true }).click();
  expect((await reviewed).status()).toBe(200);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: test.info().outputPath("source-review-viewport.png") });
  await page.screenshot({ path: test.info().outputPath("source-review-desktop.png"), fullPage: true });
});

test("desktop upload reaches a real Worker result and UTF-8 download", async ({ page }) => {
  await page.goto("/#/ingest?catalog=workspace");
  await page.getByLabel("开发身份标识").fill(context.user_id);
  await page.getByLabel("显示名称").fill("浏览器上传验收");
  await page.getByLabel("工作空间", { exact: true }).fill(context.workspace_name);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await page.locator(".ant-upload input[type=file]").setInputFiles({
    name: "桌面上传.txt", mimeType: "text/plain",
    buffer: Buffer.from("浏览器  上传的真实文本保留中文内容、清洗记录以及来源关联用于验收。", "utf-8"),
  });
  await page.getByPlaceholder("可选", { exact: true }).fill("浏览器上传来源");
  await page.getByRole("button", { name: "开始处理", exact: true }).click();
  await expect(page.getByRole("button", { name: "导出数据" })).toBeEnabled({ timeout: 30_000 });
  await expect(page).toHaveURL(/run_id=.+revision=|revision=.+run_id=/);
  await page.getByRole("button", { name: "导出数据" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.getByRole("menuitem", { name: "JSONL", exact: true }).click(),
  ]);
  expect(readFileSync((await download.path())!, "utf-8")).toContain("浏览器 上传的真实文本");
  await page.screenshot({ path: test.info().outputPath("upload-worker-desktop.png"), fullPage: true });
});
