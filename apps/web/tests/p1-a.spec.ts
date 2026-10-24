import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("P1-A 真实处理算子链和版本化产物", async ({ page }) => {
  test.setTimeout(120_000);
  const suffix = Date.now().toString();
  const auth = await page.request.post("/api/v1/auth/session", {
    data: { user_id: `p1a-${suffix}`, display_name: "P1-A operator", workspace_name: `P1-A ${suffix}` },
  });
  expect(auth.ok()).toBeTruthy();
  const session = await auth.json();
  const headers = { Authorization: `Bearer ${session.token}`, "X-Workspace-ID": session.workspace_id };
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const source = await page.request.post("/api/v1/sources", { headers: jsonHeaders, data: { name: "P1-A fixtures", kind: "upload" } });
  expect(source.ok()).toBeTruthy();
  const sourceBody = await source.json();
  const fixture = fs.readFileSync(path.join(process.cwd(), "../..", "tests/fixtures/p1a/plain_text.pdf"));
  const init = await page.request.post("/api/v1/uploads/init", { headers: jsonHeaders, data: { filename: "p1a-plain.pdf", size: fixture.length, content_type: "application/pdf" } });
  expect(init.ok()).toBeTruthy();
  const upload = await init.json();
  const put = await page.request.put(`/api/v1/uploads/${upload.upload_id}/content`, { headers: { ...headers, "Content-Type": "application/pdf" }, data: fixture });
  expect(put.ok()).toBeTruthy();
  const checksum = (await put.json()).sha256;
  expect((await page.request.post(`/api/v1/uploads/${upload.upload_id}/complete`, { headers: jsonHeaders, data: { checksum } })).ok()).toBeTruthy();
  const ingest = await page.request.post("/api/v1/ingest-batches", { headers: jsonHeaders, data: { upload_ids: [upload.upload_id], source_id: sourceBody.source_id } });
  expect(ingest.ok()).toBeTruthy();
  const asset = (await ingest.json()).items[0].asset_id;
  const runResponse = await page.request.post("/api/v1/pipeline-runs/batches", {
    headers: { ...jsonHeaders, "Idempotency-Key": `p1a-${suffix}` },
    data: { asset_ids: [asset], config: { operators: [
      { key: "builtin.clean", config: { collapse_whitespace: true } },
      { key: "builtin.deduplicate", config: { lowercase: true } },
      { key: "builtin.quality", config: { min_chars: 10 } },
    ] } },
  });
  expect(runResponse.ok()).toBeTruthy();
  const runId = (await runResponse.json()).accepted[0].run_id as string;
  let run: { status: string; nodes?: Array<{ node_id: string; status: string; output_count: number }> } = { status: "queued" };
  for (let attempt = 0; attempt < 60 && !["succeeded", "failed"].includes(run.status); attempt += 1) {
    await page.waitForTimeout(500);
    run = await (await page.request.get(`/api/v1/pipeline-runs/${runId}`, { headers })).json();
  }
  expect(run.status, JSON.stringify(run)).toBe("succeeded");
  expect(run.nodes?.map(node => node.node_id)).toEqual(expect.arrayContaining(["parse", "clean", "deduplicate", "quality"]));
  expect(run.nodes?.every(node => node.status === "succeeded")).toBeTruthy();
  const artifacts = await page.request.get(`/api/v1/pipeline-runs/${runId}/artifacts`, { headers });
  expect(artifacts.ok()).toBeTruthy();
  expect((await artifacts.json()).items.map((item: { kind: string }) => item.kind)).toEqual(expect.arrayContaining(["operator_clean", "operator_deduplicate", "operator_quality"]));
  const detail = await page.request.get(`/api/v1/assets/${asset}`, { headers });
  expect(detail.ok()).toBeTruthy();
  const versions = (await detail.json()).versions;
  expect(versions.length).toBeGreaterThanOrEqual(1);
  expect(versions[0].parser_name).toBe("builtin.pdf");
  expect(versions.some((version: { segments: Array<{ location: Record<string, unknown> }> }) => version.segments.some(segment => Object.keys(segment.location).length > 0))).toBeTruthy();
});
