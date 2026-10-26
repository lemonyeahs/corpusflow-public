import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test.describe("P0-I 系统级真实 API 验收", () => {
  test("尺寸校验、损坏 PDF、幂等 Run、审核门控和角色隔离", async ({ page }) => {
    test.setTimeout(120_000);
    const suffix = Date.now().toString();
    const adminToken = `p0i-admin-${suffix}`;
    const workspaceName = `P0-I ${suffix}`;
    const auth = await page.request.post("/api/v1/auth/session", {
      data: { user_id: adminToken, display_name: "P0-I admin", workspace_name: workspaceName },
    });
    expect(auth.ok()).toBeTruthy();
    const admin = await auth.json();
    const headers = {
      Authorization: `Bearer ${admin.token}`,
      "X-Workspace-ID": admin.workspace_id,
    };
    const jsonHeaders = { ...headers, "Content-Type": "application/json" };

    await page.goto("/");
    await page.evaluate((session) => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(session)), admin);
    await page.reload();
    await expect(page.getByRole("heading", { name: "训练数据中心", exact: true })).toBeVisible();

    const sourceResponse = await page.request.post("/api/v1/sources", {
      headers: jsonHeaders,
      data: { name: "P0-I corrupted PDFs", kind: "upload" },
    });
    expect(sourceResponse.ok()).toBeTruthy();
    const source = await sourceResponse.json();

    const corrupt = Buffer.from("this is not a PDF");
    const initResponse = await page.request.post("/api/v1/uploads/init", {
      headers: jsonHeaders,
      data: { filename: "corrupt.pdf", size: corrupt.length + 1, content_type: "application/pdf" },
    });
    expect(initResponse.ok()).toBeTruthy();
    const upload = await initResponse.json();
    const wrongSize = await page.request.put(`/api/v1/uploads/${upload.upload_id}/content`, {
      headers: { ...headers, "Content-Type": "application/pdf" },
      data: corrupt,
    });
    expect(wrongSize.status()).toBe(422);
    expect((await wrongSize.json()).error.code).toBe("UPLOAD_SIZE_MISMATCH");

    const correctInitResponse = await page.request.post("/api/v1/uploads/init", {
      headers: jsonHeaders,
      data: { filename: "corrupt.pdf", size: corrupt.length, content_type: "application/pdf" },
    });
    const correctUpload = await correctInitResponse.json();
    const uploaded = await page.request.put(`/api/v1/uploads/${correctUpload.upload_id}/content`, {
      headers: { ...headers, "Content-Type": "application/pdf" },
      data: corrupt,
    });
    expect(uploaded.ok()).toBeTruthy();
    const checksum = (await uploaded.json()).sha256;
    const completed = await page.request.post(`/api/v1/uploads/${correctUpload.upload_id}/complete`, {
      headers: jsonHeaders,
      data: { checksum },
    });
    expect(completed.ok()).toBeTruthy();
    const completedAgain = await page.request.post(`/api/v1/uploads/${correctUpload.upload_id}/complete`, {
      headers: jsonHeaders,
      data: { checksum },
    });
    expect(completedAgain.ok()).toBeTruthy();

    const ingestResponse = await page.request.post("/api/v1/ingest-batches", {
      headers: jsonHeaders,
      data: { upload_ids: [correctUpload.upload_id], source_id: source.source_id },
    });
    expect(ingestResponse.ok()).toBeTruthy();
    const asset = (await ingestResponse.json()).items[0].asset_id;
    const idempotencyKey = `p0i-run-${suffix}`;
    const firstBatchResponse = await page.request.post("/api/v1/pipeline-runs/batches", {
      headers: { ...jsonHeaders, "Idempotency-Key": idempotencyKey },
      data: { asset_ids: [asset], config: { p0i: true } },
    });
    expect(firstBatchResponse.ok()).toBeTruthy();
    const firstBatch = await firstBatchResponse.json();
    const secondBatchResponse = await page.request.post("/api/v1/pipeline-runs/batches", {
      headers: { ...jsonHeaders, "Idempotency-Key": idempotencyKey },
      data: { asset_ids: [asset], config: { p0i: true } },
    });
    expect(secondBatchResponse.ok()).toBeTruthy();
    const secondBatch = await secondBatchResponse.json();
    expect(secondBatch.batch_id).toBe(firstBatch.batch_id);
    expect(secondBatch.accepted).toHaveLength(1);
    const changedKey = await page.request.post("/api/v1/pipeline-runs/batches", {
      headers: { ...jsonHeaders, "Idempotency-Key": idempotencyKey },
      data: { asset_ids: [asset], config: { changed: true } },
    });
    expect(changedKey.status()).toBe(409);
    expect((await changedKey.json()).error.code).toBe("IDEMPOTENCY_KEY_REUSED");

    const runId = firstBatch.accepted[0].run_id;
    let status = "queued";
    for (let attempt = 0; attempt < 30 && status !== "failed"; attempt += 1) {
      await page.waitForTimeout(500);
      const response = await page.request.get(`/api/v1/pipeline-runs/${runId}`, { headers });
      status = (await response.json()).status;
    }
    expect(status).toBe("failed");
    const logs = await page.request.get(`/api/v1/pipeline-runs/${runId}/logs`, { headers });
    expect(logs.ok()).toBeTruthy();
    expect((await logs.json()).items.some((item: { message: string }) => item.message.includes("CORRUPT_PDF"))).toBeTruthy();

    const reviewerToken = `p0i-reviewer-${suffix}`;
    const reviewerResponse = await page.request.post("/api/v1/auth/session", {
      data: { user_id: reviewerToken, display_name: "P0-I reviewer", workspace_name: `reviewer-${suffix}` },
    });
    const reviewer = await reviewerResponse.json();
    const member = await page.request.post(`/api/v1/workspaces/${admin.workspace_id}/members`, {
      headers: jsonHeaders,
      data: { user_id: reviewerToken, role: "reviewer" },
    });
    expect(member.ok()).toBeTruthy();
    const issueResponse = await page.request.post("/api/v1/quality/issues", {
      headers: jsonHeaders,
      data: { run_id: runId, asset_id: asset, reason: "P0-I recovery gate", severity: "high" },
    });
    expect(issueResponse.ok()).toBeTruthy();
    const issue = await issueResponse.json();
    const reviewerHeaders = {
      Authorization: `Bearer ${reviewer.token}`,
      "X-Workspace-ID": admin.workspace_id,
      "Content-Type": "application/json",
    };
    const review = await page.request.post(`/api/v1/quality/issues/${issue.issue_id}/reviews`, {
      headers: reviewerHeaders,
      data: { decision: "rejected", note: "cannot recover" },
    });
    expect(review.ok()).toBeTruthy();
    const blocked = await page.request.post(`/api/v1/pipeline-runs/${runId}/resume`, { headers: jsonHeaders, data: {} });
    expect(blocked.status()).toBe(409);
    expect((await blocked.json()).error.code).toBe("RUN_REVIEW_BLOCKED");

    const viewerToken = `p0i-viewer-${suffix}`;
    const viewerResponse = await page.request.post("/api/v1/auth/session", {
      data: { user_id: viewerToken, display_name: "P0-I viewer", workspace_name: `viewer-${suffix}` },
    });
    expect(viewerResponse.ok()).toBeTruthy();
    const viewerMembership = await page.request.post(`/api/v1/workspaces/${admin.workspace_id}/members`, {
      headers: jsonHeaders,
      data: { user_id: viewerToken, role: "viewer" },
    });
    expect(viewerMembership.ok()).toBeTruthy();
    const viewer = await viewerResponse.json();
    const viewerCreate = await page.request.post("/api/v1/sources", {
      headers: { Authorization: `Bearer ${viewer.token}`, "X-Workspace-ID": admin.workspace_id, "Content-Type": "application/json" },
      data: { name: "must be denied", kind: "upload" },
    });
    expect(viewerCreate.status()).toBe(403);

    const outsiderResponse = await page.request.post("/api/v1/auth/session", {
      data: { user_id: `p0i-outsider-${suffix}`, display_name: "P0-I outsider", workspace_name: `outside-${suffix}` },
    });
    const outsider = await outsiderResponse.json();
    const crossWorkspace = await page.request.get(`/api/v1/assets/${asset}`, {
      headers: { Authorization: `Bearer ${outsider.token}`, "X-Workspace-ID": outsider.workspace_id },
    });
    expect(crossWorkspace.status()).toBe(404);
    const metrics = await page.request.get("/api/v1/ops/metrics", { headers });
    expect(metrics.ok()).toBeTruthy();
    const viewerMetrics = await page.request.get("/api/v1/ops/metrics", {
      headers: { Authorization: `Bearer ${viewer.token}`, "X-Workspace-ID": admin.workspace_id },
    });
    expect(viewerMetrics.status()).toBe(403);

    const fixture = fs.readFileSync(path.join(process.cwd(), "tests/fixtures/corpusflow-e2e.pdf"));
    expect(fixture.byteLength).toBeGreaterThan(100);
  });
});
