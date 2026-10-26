import { expect, test } from "@playwright/test";

test("real session login, authenticated deep link, refresh and logout", async ({ page }) => {
  await page.goto("/#/data/pdf?catalog=workspace&q=hello&offset=20");
  await page.getByLabel("开发身份标识").fill("m0-live-browser");
  await page.getByLabel("显示名称").fill("M0 验收");
  await page.getByLabel("工作空间", { exact: true }).fill("M0 isolated browser");
  const sessionResponse = page.waitForResponse(response => response.url().endsWith("/auth/session"));
  await page.getByRole("button", { name: "进入工作台" }).click();
  expect((await sessionResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "数据台", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/data\/pdf\?catalog=workspace&q=hello&offset=20$/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "数据台", exact: true })).toBeVisible();
  await page.goto("/#/advanced/assets");
  await expect(page.getByText("暂无资产。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("button", { name: "进入工作台" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("corpusflow.p0h.session"))).toBeNull();
});

test("real memberships override stored role, isolate workspace and revalidate switching", async ({ page, request }) => {
  const create = async (user: string) => {
    const response = await request.post("/api/v1/auth/session", { data: { user_id: user, display_name: user, workspace_name: user } });
    expect(response.status()).toBe(200);
    return response.json();
  };
  const admin = await create("m0-live-admin");
  const viewer = await create("m0-live-viewer");
  const forbidden = await request.get("/api/v1/sources", { headers: { Authorization: `Bearer ${viewer.token}`, "X-Workspace-ID": admin.workspace_id } });
  expect(forbidden.status()).toBe(403);
  const member = await request.post(`/api/v1/workspaces/${admin.workspace_id}/members`, { headers: { Authorization: `Bearer ${admin.token}`, "X-Workspace-ID": admin.workspace_id }, data: { user_id: viewer.token, role: "viewer" } });
  expect(member.status()).toBe(200);
  await page.goto("/");
  await page.evaluate(value => localStorage.setItem("corpusflow.p0h.session", JSON.stringify(value)), { ...viewer, workspace_id: admin.workspace_id, role: "admin" });
  await page.goto("/#/ingest?catalog=workspace");
  await page.reload();
  await expect(page.getByRole("heading", { name: "没有访问权限" })).toBeVisible();
  await page.getByLabel("切换工作空间").selectOption(viewer.workspace_id);
  await expect(page.getByRole("heading", { name: "训练数据中心" })).toBeVisible();
  await page.goto("/#/ingest?catalog=workspace");
  await expect(page.getByRole("heading", { name: "数据接入", exact: true })).toBeVisible();
  await page.evaluate(() => { const key = "corpusflow.p0h.session"; const stored = JSON.parse(localStorage.getItem(key)!); localStorage.setItem(key, JSON.stringify({ ...stored, workspace_id: "unassigned-workspace" })); });
  await page.reload();
  await expect(page.getByText("当前身份无法访问此工作空间", { exact: true })).toBeVisible();
});

test("real backend authorization failure never becomes example data", async ({ page, request }) => {
  const response = await request.get("/api/v1/sources");
  expect(response.status()).toBe(401);
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const path = "/src/api/client.ts";
    const { request } = await import(path);
    try { await request("/training-center/files?catalog=generated", { token: "invalid", workspaceId: "invalid" }); return null; }
    catch (error) { return { code: (error as { code: string }).code, status: (error as { status: number }).status }; }
  });
  expect(result).toEqual({ code: "UNAUTHENTICATED", status: 401 });
});
