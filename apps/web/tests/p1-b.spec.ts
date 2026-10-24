import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("P1-B RAG 产品在 Web 页面真实构建并进入发布下载", async ({ page }) => {
  test.setTimeout(180_000);
  const suffix = Date.now().toString();
  const auth = await page.request.post("/api/v1/auth/session", { data: { user_id: `p1b-web-${suffix}`, display_name: "P1-B Web", workspace_name: `P1-B Web ${suffix}` } });
  const session = await auth.json();
  const headers = { Authorization: `Bearer ${session.token}`, "X-Workspace-ID": session.workspace_id };
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const source = await page.request.post("/api/v1/sources", { headers: jsonHeaders, data: { name: "P1-B Web fixture", kind: "upload" } });
  const sourceId = (await source.json()).source_id as string;
  const fixture = fs.readFileSync(path.join(process.cwd(), "../..", "tests/fixtures/p1a/plain_text.pdf"));
  const init = await page.request.post("/api/v1/uploads/init", { headers: jsonHeaders, data: { filename: "p1b-web.pdf", size: fixture.length, content_type: "application/pdf" } });
  const upload = await init.json();
  const put = await page.request.put(`/api/v1/uploads/${upload.upload_id}/content`, { headers: { ...headers, "Content-Type": "application/pdf" }, data: fixture });
  const checksum = (await put.json()).sha256 as string;
  await page.request.post(`/api/v1/uploads/${upload.upload_id}/complete`, { headers: jsonHeaders, data: { checksum } });
  const ingest = await page.request.post("/api/v1/ingest-batches", { headers: jsonHeaders, data: { upload_ids: [upload.upload_id], source_id: sourceId } });
  const assetId = (await ingest.json()).items[0].asset_id as string;
  const run = await page.request.post("/api/v1/pipeline-runs/batches", { headers: jsonHeaders, data: { asset_ids: [assetId], config: {} } });
  const runId = (await run.json()).accepted[0].run_id as string;
  let status = "queued";
  for (let attempt = 0; attempt < 60 && !["succeeded", "failed"].includes(status); attempt += 1) {
    await page.waitForTimeout(400);
    status = (await (await page.request.get(`/api/v1/pipeline-runs/${runId}`, { headers })).json()).status;
  }
  expect(status).toBe("succeeded");
  const detail = await page.request.get(`/api/v1/assets/${assetId}`, { headers });
  const segmentId = (await detail.json()).versions[0].segments[0].segment_id as string;
  await page.request.post("/api/v1/authorization/grants", { headers: jsonHeaders, data: { asset_id: assetId, purpose: "rag", evidence_uri: `p1b-web://${suffix}`, legal_basis: "isolated fixture" } });
  const reviewerAuth = await page.request.post("/api/v1/auth/session", { data: { user_id: `p1b-reviewer-${suffix}`, display_name: "P1-B reviewer", workspace_name: `P1-B reviewer ${suffix}` } });
  const reviewer = await reviewerAuth.json();
  const membership = await page.request.post(`/api/v1/workspaces/${session.workspace_id}/members`, { headers: jsonHeaders, data: { user_id: `p1b-reviewer-${suffix}`, role: "reviewer" } });
  expect(membership.ok(), await membership.text()).toBeTruthy();

  await page.goto("/");
  await page.evaluate((value) => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), session);
  await page.reload();
  await page.getByRole("button", { name: "SFT 产品" }).click();
  await page.getByLabel("产品类型").selectOption("rag");
  await page.getByRole("button", { name: "创建 RAG 产品" }).click();
  await page.getByLabel("Segment ID（逗号或换行分隔）").fill(segmentId);
  await page.getByLabel("Chunk Size（token）").fill("2");
  await page.getByLabel("Overlap（token）").fill("1");
  await page.getByRole("button", { name: "预览授权范围" }).click();
  await expect(page.getByText(/预览结果/)).toBeVisible();
  const buildResponsePromise = page.waitForResponse(response => response.url().endsWith("/api/v1/dataset-builds") && response.request().method() === "POST");
  await page.getByRole("button", { name: "创建构建快照" }).click();
  const buildResponse = await buildResponsePromise;
  expect(buildResponse.ok(), await buildResponse.text()).toBeTruthy();
  const buildBody = await buildResponse.json() as { build_id: string };
  await expect(page.getByText(/Build /)).toBeVisible();
  const buildCandidates = await page.request.get(`/api/v1/dataset-builds/${buildBody.build_id}/candidates`, { headers });
  expect(buildCandidates.ok()).toBeTruthy();
  const samples = (await buildCandidates.json()).items as Array<{ sample_id: string }>;
  for (const sample of samples) {
    const reviewResponse = await page.request.post(`/api/v1/candidate-samples/${sample.sample_id}/reviews`, { headers: { Authorization: `Bearer ${reviewer.token}`, "X-Workspace-ID": session.workspace_id, "Content-Type": "application/json" }, data: { decision: "approved", note: "P1-B Web review" } });
    expect(reviewResponse.ok(), await reviewResponse.text()).toBeTruthy();
  }
  await page.getByRole("button", { name: "服务端验证快照" }).click();
  await expect(page.getByText("validated", { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("版本").fill("3.0.0");
  await page.getByRole("button", { name: "发布不可变版本" }).click();
  await expect(page.getByRole("heading", { name: "数据集发布与下载" })).toBeVisible();
  await page.getByRole("button", { name: "Manifest" }).first().click();
  await expect(page.getByText("内容 SHA-256")).toBeVisible();
});

