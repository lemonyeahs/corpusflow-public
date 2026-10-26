import { expect, test } from "@playwright/test";

test("shared B/C/D examples preserve paging, snapshot, errors and explicit processing opt-in", async ({ page }) => {
  test.skip(process.env.M0_FIXTURES !== "true" || (process.env.M0_SCENARIO || "success") !== "success");
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const path = "/src/dev/training-center/interceptor.ts";
    const { fixtureResponse } = await import(path);
    const fixturePath = "/src/dev/training-center/fixtures.ts";
    const { graph } = await import(fixturePath);
    const root = graph("success").root;
    const headers = new Headers({ "X-Workspace-ID": "verified-test-space" });
    const call = async (url: string, method = "GET") => {
      const response = fixtureResponse(url, headers, { method });
      return response ? { status: response.status, body: await response.json() } : null;
    };
    const list = (await call("/training-center/datasets"))!.body;
    const cpt = list.items.find((item: { kind: string }) => item.kind === "cpt");
    const base = `/training-center/datasets/${cpt.id}/samples?version=${cpt.version}`;
    return {
      list, page2: await call(`${base}&offset=20`), emptySearch: await call(`${base}&q=no-matching-text`),
      expired: await call(`${base}&revision=expired`), invalid: await call("/training-center/files?limit=101"),
      unsupportedFilter: await call("/training-center/formats/txt/stats?language=en"),
      graph: await call(`/lineage/graph?root_type=${root.type}&root_id=${root.id}&max_nodes=1`),
      missingRoot: await call("/lineage/graph"), missingVersion: await call(`/training-center/datasets/${cpt.id}/samples`),
      emptyLimit: await call("/training-center/files?limit="),
      processing: await call("/pipeline-runs/m0-example-run/summary?catalog=workspace&fixture=contract-v1"),
      implicitProcessing: await call("/pipeline-runs/m0-example-run/summary?catalog=workspace"),
      realProcessing: await call("/pipeline-runs/real-run/summary?catalog=workspace&fixture=contract-v1"),
      workspace: await call("/training-center/files?catalog=workspace"), write: await call("/training-center/files", "POST"),
      badVersion: await call(`/training-center/datasets/${cpt.id}/overview?version=unknown`),
    };
  });
  if (!result.page2 || !result.emptySearch || !result.expired || !result.invalid || !result.unsupportedFilter || !result.graph || !result.missingRoot || !result.missingVersion || !result.emptyLimit || !result.processing || !result.badVersion) throw new Error("Expected an explicitly intercepted contract response");
  expect(result.list.scope.workspace_id).toBe("verified-test-space");
  expect(result.list.items.every((item: { workspace_id: string }) => item.workspace_id === "verified-test-space")).toBe(true);
  expect(result.page2.body.items).toHaveLength(3);
  expect(result.page2.body.total_count).toBe(23);
  expect(result.page2.body.offset).toBe(20);
  expect(result.emptySearch.body.total_count).toBe(0);
  expect(result.expired.status).toBe(409);
  expect(result.expired.body.error.code).toBe("SNAPSHOT_EXPIRED");
  expect(result.expired.body.request_id).toBeTruthy();
  expect(result.invalid.body.error.code).toBe("VALIDATION_FAILED");
  expect(result.unsupportedFilter.status).toBe(422);
  expect(result.graph.body.nodes).toHaveLength(1);
  expect(result.graph.body.truncation_reason).toBe("max_nodes");
  expect([result.missingRoot.status, result.missingVersion.status, result.emptyLimit.status]).toEqual([422, 422, 422]);
  expect(result.processing.body.scope.catalog).toBe("workspace");
  expect(result.processing.body.steps[0].input_count).toBe(1);
  expect([result.implicitProcessing, result.realProcessing, result.workspace, result.write]).toEqual([null, null, null, null]);
  expect(result.badVersion.status).toBe(404);
});
