import { expect, test } from "@playwright/test";

test("窄屏登录和首页无横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("开发身份标识").fill(`p0h-mobile-${Date.now()}`);
  await page.getByLabel("显示名称").fill("Mobile smoke");
  await page.getByLabel("工作空间").fill(`P0-H Mobile ${Date.now()}`);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("heading", { name: "训练数据中心", exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
