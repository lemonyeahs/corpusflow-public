import { expect, test } from "@playwright/test";
import path from "node:path";

test.describe("P0-H 真实 Web 联调", () => {
  test("登录、真实 PDF、异步解析、SFT 发布、下载和血缘", async ({ page, browser }) => {
    test.setTimeout(180_000);
    const suffix = Date.now().toString();
    const adminUser = `p0h-admin-${suffix}`;
    const workspaceName = `P0-H E2E ${suffix}`;
    await page.goto("/");
    await page.getByLabel("开发身份标识").fill(adminUser);
    await page.getByLabel("显示名称").fill("P0-H E2E 管理员");
    await page.getByLabel("工作空间").fill(workspaceName);
    await page.getByRole("button", { name: "进入工作台" }).click();
    await expect(page.getByRole("heading", { name: "工作台总览" })).toBeVisible();

    await page.getByRole("button", { name: "数据接入" }).click();
    await page.getByRole("button", { name: "创建来源" }).click();
    await page.locator('input[type="file"]').setInputFiles(path.join(process.cwd(), "tests/fixtures/corpusflow-e2e.pdf"));
    await page.getByRole("button", { name: "上传并登记批次" }).click();
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: "资产中心" }).click();
    await expect(page.getByText("corpusflow-e2e.pdf", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "处理中心" }).click();
    await page.locator('.check-row input[type="checkbox"]').first().check();
    await page.getByRole("button", { name: "创建 N 个独立 Run" }).click();
    await expect(page.getByTestId("run-status").getByText("succeeded", { exact: true })).toBeVisible({ timeout: 60_000 });

    await page.getByRole("button", { name: "资产中心" }).click();
    await page.getByText("corpusflow-e2e.pdf", { exact: true }).click();
    await expect(page.locator(".version-block")).toBeVisible({ timeout: 30_000 });
    const segmentId = (await page.locator(".segment code").first().textContent())?.trim();
    expect(segmentId).toBeTruthy();
    const assetId = (await page.locator(".detail-grid code").first().textContent())?.trim();
    expect(assetId).toBeTruthy();

    const adminSession = await page.evaluate(() => JSON.parse(localStorage.getItem("corpusflow.p0h.session") || "null"));
    expect(adminSession).toBeTruthy();
    const reviewerUserId = `p0h-reviewer-${suffix}`;
    const reviewerResponse = await page.request.post("/api/v1/auth/session", { data: { user_id: reviewerUserId, display_name: "P0-H E2E 审核员", workspace_name: `Reviewer ${suffix}` } });
    expect(reviewerResponse.ok()).toBeTruthy();
    const reviewerSession = await reviewerResponse.json();
    const memberResponse = await page.request.post(`/api/v1/workspaces/${adminSession.workspace_id}/members`, { headers: { Authorization: `Bearer ${adminSession.token}`, "X-Workspace-ID": adminSession.workspace_id }, data: { user_id: reviewerUserId, role: "reviewer" } });
    expect(memberResponse.ok(), await memberResponse.text()).toBeTruthy();
    const grantResponse = await page.request.post("/api/v1/authorization/grants", { headers: { Authorization: `Bearer ${adminSession.token}`, "X-Workspace-ID": adminSession.workspace_id }, data: { asset_id: assetId, purpose: "training", evidence_uri: `e2e://license/${suffix}`, legal_basis: "isolated test fixture" } });
    expect(grantResponse.ok(), await grantResponse.text()).toBeTruthy();

    await page.getByRole("button", { name: "SFT 产品" }).click();
    await page.getByLabel("新产品名称").fill(`E2E SFT ${suffix}`);
    await page.getByRole("button", { name: "创建 SFT 产品" }).click();
    await page.getByLabel("Segment ID（逗号或换行分隔）").fill(segmentId!);
    await page.getByRole("button", { name: "预览授权范围" }).click();
    await expect(page.getByText(/预览结果/)).toBeVisible();
    await page.getByRole("button", { name: "创建构建快照" }).click();
    await expect(page.getByText(/Build /)).toBeVisible();
    const sampleId = (await page.locator(".candidate code").first().textContent())?.trim();
    expect(sampleId).toBeTruthy();

    const reviewerContext = await browser.newContext();
    const reviewerPage = await reviewerContext.newPage();
    await reviewerPage.goto("/");
    await reviewerPage.evaluate((session) => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(session)), { ...reviewerSession, workspace_id: adminSession.workspace_id, role: "reviewer" });
    await reviewerPage.reload();
    await expect(reviewerPage.getByRole("heading", { name: "工作台总览" })).toBeVisible();
    const reviewResponse = await reviewerPage.request.post(`/api/v1/candidate-samples/${sampleId}/reviews`, { headers: { Authorization: `Bearer ${reviewerSession.token}`, "X-Workspace-ID": adminSession.workspace_id }, data: { decision: "approved", note: "E2E reviewer approval" } });
    expect(reviewResponse.ok(), await reviewResponse.text()).toBeTruthy();
    await reviewerContext.close();

    await page.getByRole("button", { name: "服务端验证快照" }).click();
    await expect(page.getByText("validated", { exact: true })).toBeVisible();
    await page.getByLabel("版本").fill("1.0.0");
    await page.getByRole("button", { name: "发布不可变版本" }).click();
    await expect(page.getByRole("heading", { name: "数据集发布与下载" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "发布下载" }).click();
    await expect(page.getByRole("button", { name: "Manifest" })).toBeVisible();
    await page.getByRole("button", { name: "Manifest" }).first().click();
    await expect(page.getByText("内容 SHA-256")).toBeVisible();

    const versionResponse = await page.request.get(`/api/v1/datasets/${(await page.locator("select").first().inputValue())}/versions`, { headers: { Authorization: `Bearer ${adminSession.token}`, "X-Workspace-ID": adminSession.workspace_id } });
    expect(versionResponse.ok()).toBeTruthy();
    const versions = await versionResponse.json();
    const version = versions.items[0];
    const downloadResponse = await page.request.get(`/api/v1/datasets/${versions.items[0] ? (await page.locator("select").first().inputValue()) : ""}/versions/${version.version}/download?purpose=training`, { headers: { Authorization: `Bearer ${adminSession.token}`, "X-Workspace-ID": adminSession.workspace_id } });
    expect(downloadResponse.ok()).toBeTruthy();
    expect((await downloadResponse.json()).url).toMatch(/Signature|X-Amz-Signature/);

    await page.getByRole("button", { name: "数据血缘" }).click();
    await page.getByLabel("对象类型").selectOption("DatasetVersion");
    await page.getByLabel("对象 ID").fill(version.dataset_version_id);
    await page.getByRole("button", { name: "查询血缘" }).click();
    await expect(page.getByText(/关联边/)).toContainText(/[1-9]/);

    const outsiderResponse = await page.request.post("/api/v1/auth/session", { data: { user_id: `p0h-outsider-${suffix}`, display_name: "P0-H outsider", workspace_name: `Outside ${suffix}` } });
    const outsider = await outsiderResponse.json();
    const denied = await page.request.get(`/api/v1/datasets/${(await page.locator("select").first().inputValue())}/versions/${version.version}/manifest`, { headers: { Authorization: `Bearer ${outsider.token}`, "X-Workspace-ID": outsider.workspace_id } });
    expect(denied.status()).toBe(404);
  });
});
