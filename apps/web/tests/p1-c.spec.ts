import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

test("P1-C real quality reports, coverage, immutable version differences and export", async ({ page }) => {
  test.setTimeout(180_000);
  const root = path.resolve(process.cwd(), "../..");
  // Generates new owned fixtures through real API/Worker/MinIO, no canned API responses.
  execFileSync(path.join(root, ".venv/bin/python"), ["scripts/verify_p1c_quality.py"], { cwd: root, timeout: 120_000 });
  const state = JSON.parse(fs.readFileSync(path.join(root, ".local/p1c/web.json"), "utf8")) as { session: { token: string; workspace_id: string }; left: string; right: string };
  await page.goto("/");
  await page.evaluate(session => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(session)), state.session);
  await page.reload();
  await page.getByRole("button", { name: "质量审核", exact: true }).click();
  await expect(page.getByRole("heading", { name: "质量规则管理" })).toBeVisible();
  await expect(page.getByText("去重资产：3", { exact: false })).toBeVisible();
  await page.getByLabel("评估目标 ID").fill(state.left);
  await page.getByRole("button", { name: "执行真实评估" }).click();
  await expect(page.getByTestId("quality-status")).toHaveText("FAIL"); // revoked training grant
  await expect(page.getByRole("cell", { name: "NOT_EVALUATED", exact: true }).first()).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出质量 JSON" }).click();
  const download = await downloadPromise;
  const exported = JSON.parse(fs.readFileSync((await download.path())!, "utf8"));
  expect(exported.report.dataset_version_id).toBe(state.left);
  expect(exported.report.authorization_gate).toBe("FAIL");
  await page.getByLabel("左侧版本 ID").fill(state.left);
  await page.getByLabel("右侧版本 ID").fill(state.right);
  await page.getByRole("button", { name: "比较发布版本" }).click();
  await expect(page.getByText("COMPARABLE", { exact: true })).toBeVisible();
  await page.getByText("样本、配置、Manifest、来源与领域变化", { exact: true }).click();
  await expect(page.getByText('"manifest_diff"', { exact: false }).last()).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "质量审核", exact: true }).click();
  await expect(page.getByLabel("历史评估").locator("option")).not.toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "执行真实评估" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
