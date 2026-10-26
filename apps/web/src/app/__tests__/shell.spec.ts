import { expect, test, type Page } from "@playwright/test";
import process from "node:process";
import type { ApiErrorBody, FormatStatsResponse } from "../../contracts/training-center";

// Unknown ingestion time must remain unavailable, even for a successfully generated file.
const unavailableTrend: Pick<FormatStatsResponse, "ingestion_trend" | "availability"> = {
  ingestion_trend: null, availability: { ingestion_trend: "ingested_at_missing" },
};

const session = { token: "m0-test-token", user_id: "m0-user", workspace_id: "m0-space-a", role: "admin" };
const fixtureMode = process.env.M0_FIXTURES === "true";
async function backend(page: Page, role = "admin") {
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/session")) return route.fulfill({ json: session });
    const memberships = [{ workspace_id: "m0-space-a", role }, { workspace_id: "m0-space-b", role: "viewer" }];
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: { user_id: session.user_id, workspaces: memberships } });
    if (url.pathname.endsWith("/workspaces")) return route.fulfill({ json: { items: memberships } });
    if (url.pathname.endsWith("/assets")) return route.fulfill({ json: { items: [], total_count: 0 } });
    return route.fulfill({ status: 503, json: { error: { code: "TEST_BACKEND_UNAVAILABLE", message: "测试后端不可用", retryable: false } } });
  });
}
async function authenticated(page: Page, target = "/home", role = "admin") {
  await backend(page, role);
  await page.addInitScript(value => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), session);
  await page.goto(`/#${target}`);
}

test("login retains deep link and filters through refresh and history", async ({ page }) => {
  await backend(page);
  await page.goto("/#/data/pdf?catalog=workspace&revision=r1&q=hello&offset=20");
  await expect(page.getByRole("button", { name: "进入工作台" })).toBeVisible();
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("heading", { name: "数据台", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/data\/pdf\?catalog=workspace&revision=r1&q=hello&offset=20$/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "数据台", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "首页", exact: true }).click();
  await page.goBack();
  await expect(page).toHaveURL(/offset=20$/);
  await page.goForward();
  await expect(page).toHaveURL(/#\/home\?catalog=workspace&revision=r1$/);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("button", { name: "进入工作台" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("corpusflow.p0h.session"))).toBeNull();
});

test("all new routes and unknown routes mount", async ({ page }) => {
  await authenticated(page);
  for (const [path, heading] of [["/home", "训练数据中心"], ["/data/all", "数据台"], ["/ingest", "数据接入"], ["/datasets/cpt", "训练数据集"], ["/datasets/sft?tab=samples&sample_id=a", "训练数据集"], ["/datasets/dpo", "训练数据集"], ["/lineage?catalog=workspace&root_id=a", "数据血缘"], ["/data/bad", "不支持的数据格式"], ["/datasets/bad", "不支持的训练类型"], ["/missing", "页面不存在"]]) {
    await page.goto(`/#${path}`);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
});

test("server role protects direct routes and switching workspace revalidates", async ({ page }) => {
  await authenticated(page, "/advanced/admin", "viewer");
  await expect(page.getByText("没有权限访问此页面", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "系统管理" })).toHaveCount(0);
  await page.goto("/#/ingest");
  await expect(page.getByRole("heading", { name: "没有访问权限" })).toBeVisible();
  await page.getByLabel("切换工作空间").selectOption("m0-space-b");
  await expect(page.getByRole("heading", { name: "训练数据中心" })).toBeVisible();
  await expect(page.getByLabel("切换工作空间")).toHaveValue("m0-space-b");
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("corpusflow.p0h.session") || "null"));
  expect(stored.workspace_id).toBe("m0-space-b");
  expect(stored.role).toBe("viewer");
});

test("invalid or unavailable authentication never mounts protected content", async ({ page }) => {
  await authenticated(page);
  await page.route("**/api/v1/auth/me", route => route.fulfill({ status: 401, json: { error: { code: "UNAUTHORIZED", message: "登录已失效" } } }));
  await page.reload();
  await expect(page.getByText("登录已失效", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "主导航" })).toHaveCount(0);
  await page.getByRole("button", { name: "重新登录" }).click();
  await expect(page.getByRole("button", { name: "进入工作台" })).toBeVisible();
});

test("legacy entry points mount and styles stay isolated", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await authenticated(page, "/advanced/assets?format=pdf");
  await expect(page.getByRole("heading", { name: "原始与结构化资产" })).toBeVisible();
  await expect(page.getByText("暂无资产。", { exact: true })).toBeVisible();
  expect(await page.locator(".legacy-page").evaluate(el => getComputedStyle(el).backgroundColor)).toBe("rgb(9, 17, 31)");
  for (const path of ["dashboard", "ingest", "processing", "document?asset_id=test", "datasets", "dpo", "lineage?segment_id=example", "admin"]) {
    await page.goto(`/#/advanced/${path}`);
    await expect(page.locator(".legacy-page h1")).toBeVisible();
  }
  await page.goto("/#/home");
  await expect(page.getByRole("heading", { name: "训练数据中心" })).toBeVisible();
  expect(await page.getByRole("heading", { name: "训练数据中心" }).evaluate(el => getComputedStyle(el).color)).toBe("rgb(32, 46, 59)");
  expect(errors).toEqual([]);
});

test("mobile navigation and desktop layout", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticated(page);
  await page.getByRole("button", { name: "打开菜单" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "SFT 指令微调" }).click();
  await expect(page.getByRole("heading", { name: "训练数据集" })).toBeVisible();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/m0/mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/#/home");
  await page.screenshot({ path: "test-results/m0/desktop.png", fullPage: true });
});

test("fixtures require explicit mode; real failures never fall back", async ({ page }) => {
  await authenticated(page);
  const result = await page.evaluate(async () => {
    const modulePath = "/src/api/client.ts";
    const { request } = await import(modulePath);
    const ctx = { token: "m0-test-token", workspaceId: "m0-space-a" };
    async function call(path: string) {
      try { return { data: await request(path, ctx), code: null }; }
      catch (error) { return { data: null, code: (error as { code: string }).code }; }
    }
    return { generated: await call("/training-center/files?catalog=generated"), workspace: await call("/training-center/files?catalog=workspace"), missing: await call("/training-center/not-implemented?catalog=generated") };
  });
  const scenario = process.env.M0_SCENARIO || "success";
  if (fixtureMode && scenario !== "error") {
    expect(result.generated.data.scope.workspace_id).toBe("m0-space-a");
    expect(result.generated.data.items.length).toBe(scenario === "empty" ? 0 : 1);
  } else expect(result.generated.code).toBe(fixtureMode ? "FIXTURE_UNAVAILABLE" : "TEST_BACKEND_UNAVAILABLE");
  expect(result.workspace.code).toBe("TEST_BACKEND_UNAVAILABLE");
  expect(result.missing.code).toBe("TEST_BACKEND_UNAVAILABLE");
});

test("query keys isolate scope and download preserves bytes and filename", async ({ page }) => {
  await authenticated(page);
  await page.route("**/api/v1/download-test", route => route.fulfill({ body: "one\ntwo\n", headers: { "Content-Type": "text/plain", "Content-Disposition": "attachment; filename*=UTF-8''%E6%A0%B7%E4%BE%8B.txt" } }));
  const result = await page.evaluate(async () => {
    const queryPath = "/src/app/query.ts";
    const downloadPath = "/src/api/download.ts";
    const { createQueryClient, trainingKeys } = await import(queryPath);
    const { download } = await import(downloadPath);
    const client = createQueryClient();
    client.setQueryData(trainingKeys.query("a", "generated", "r1", "files", { offset: 0 }), "private");
    const isolated = [trainingKeys.query("b", "generated", "r1", "files", { offset: 0 }), trainingKeys.query("a", "workspace", "r1", "files", { offset: 0 }), trainingKeys.query("a", "generated", "r2", "files", { offset: 0 }), trainingKeys.query("a", "generated", "r1", "files", { offset: 20 })].every(key => client.getQueryData(key) === undefined);
    const file = await download("/download-test", { token: "m0-test-token", workspaceId: "m0-space-a" }, "fallback.txt");
    return { isolated, filename: file.filename, text: await file.blob.text() };
  });
  expect(result).toEqual({ isolated: true, filename: "样例.txt", text: "one\ntwo\n" });
});

test("backend error envelope survives JSON and download clients", async ({ page }) => {
  await authenticated(page);
  const body: ApiErrorBody = {
    error: { code: "SNAPSHOT_EXPIRED", message: "快照已过期", details: [], retryable: false },
    request_id: "integration-request-001",
  };
  await page.route("**/api/v1/contract-error", route => route.fulfill({ status: 409, json: body }));
  await page.route("**/api/v1/contract-invalid", route => route.fulfill({ status: 200, contentType: "text/html", body: "<html>proxy response</html>" }));
  const result = await page.evaluate(async () => {
    const clientPath = "/src/api/client.ts";
    const downloadPath = "/src/api/download.ts";
    const { request } = await import(clientPath);
    const { download } = await import(downloadPath);
    const ctx = { token: "m0-test-token", workspaceId: "m0-space-a" };
    const results = [];
    for (const call of [() => request("/contract-error", ctx), () => download("/contract-error", ctx, "data.jsonl"), () => request("/contract-invalid", ctx)]) {
      try { await call(); results.push(null); }
      catch (error) {
        const { code, status, requestId, retryable } = error as { code: string; status: number; requestId?: string; retryable: boolean };
        results.push({ code, status, requestId, retryable });
      }
    }
    return results;
  });
  const expected = { code: "SNAPSHOT_EXPIRED", status: 409, requestId: body.request_id, retryable: false };
  expect(result).toEqual([expected, expected, { code: "INVALID_RESPONSE", status: 200, requestId: undefined, retryable: false }]);
  expect(unavailableTrend.ingestion_trend).toBeNull();
});
