import { expect, test } from "@playwright/test";

// Opt in only against a disposable backend. Never seed the production service.
const backend = process.env.OPENFIC_REVIEW_QA_BACKEND;
const frontend = process.env.OPENFIC_REVIEW_QA_FRONTEND ?? "http://127.0.0.1:19000";
test.skip(!backend, "Requires OPENFIC_REVIEW_QA_BACKEND with isolated data");
test.use({ channel: process.env.OPENFIC_QA_BROWSER, video: "off" });

test("review scroll, edit, stale save and versioned adoption", async ({ page, request }) => {
  if (!backend || new URL(backend).port === "18081") throw new Error("Use an isolated backend");
  const projectResponse = await request.post(`${backend}/api/v1/projects`, {
    multipart: { title: "QA：待审修订与滚动" },
  });
  expect(projectResponse.status()).toBe(201);
  const project = await projectResponse.json();
  const root = `${backend}/api/v1/projects/${project.id}/pending-changes`;
  const before = Array.from(
    { length: 55 },
    (_, i) => `## 第 ${i + 1} 段\n\n“保留原文”：这是用于滚动核验的长段落。`,
  ).join("\n\n");
  const created = await (
    await request.post(root, {
      data: {
        target_type: "character",
        operation: "create",
        after: { title: "测试角色", body: before },
      },
    })
  ).json();
  const applied = await (await request.post(`${root}/${created.id}/apply`)).json();
  const proposed = await (
    await request.post(root, {
      data: {
        target_type: "character",
        target_id: applied.target_id,
        operation: "update",
        after: { body: `新增开场。\n\n${before}\n\n新增收尾。` },
      },
    })
  ).json();
  await page.route("**/api/**", async (route) => {
    const original = new URL(route.request().url());
    const response = await route.fetch({ url: `${backend}${original.pathname}${original.search}` });
    await route.fulfill({ response });
  });
  await page.goto(`${frontend}/projects/${project.id}/changes?change=${proposed.id}`);
  const panes = page.locator(".pending-project-changes-body-version-content");
  await expect(panes).toHaveCount(2);
  const positions = () => panes.evaluateAll((nodes) => nodes.map((node) => node.scrollTop));
  await expect
    .poll(() => panes.first().evaluate((node) => node.scrollHeight > node.clientHeight))
    .toBe(true);
  await panes.first().hover();
  await page.mouse.wheel(0, 160);
  await expect.poll(async () => (await positions())[0]).toBeGreaterThan(0);
  expect((await positions())[1]).toBe(0);
  const initial = await positions();
  await page.locator(".pending-body-legend").hover();
  await page.mouse.wheel(0, 180);
  await expect.poll(async () => (await positions())[1]).toBeGreaterThan(0);
  const joint = await positions();
  expect(Math.abs(joint[0] - initial[0] - (joint[1] - initial[1]))).toBeLessThan(2);
  await panes.first().evaluate((node) => {
    node.scrollTop = node.scrollHeight;
  });
  const right = (await positions())[1];
  await page.locator(".pending-body-legend").hover();
  await page.mouse.wheel(0, 120);
  await expect.poll(async () => (await positions())[1]).toBeGreaterThan(right);
  await page.screenshot({ path: "../tmp/pending-review-view.png", fullPage: true });

  await page.getByRole("button", { name: "编辑待采用版本", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "编辑待采用正文", exact: true });
  await editor.fill("我保留好的部分，补齐其余内容。\n\n“修订完成”。");
  await expect(page.getByRole("button", { name: "采用", exact: true })).toBeDisabled();
  await page.screenshot({ path: "../tmp/pending-review-edit.png", fullPage: true });
  await page.getByRole("button", { name: "保存待审", exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(panes.last()).toContainText("修订完成");
  const saved = await (await request.get(`${root}/${proposed.id}`)).json();
  expect(saved.status).toBe("pending");
  expect(saved.before).toEqual(proposed.before);

  const narrowContext = await page
    .context()
    .browser()!
    .newContext({
      viewport: { width: 820, height: 900 },
      colorScheme: "dark",
    });
  try {
    await narrowContext.route("**/api/**", async (route) => {
      const original = new URL(route.request().url());
      const response = await route.fetch({
        url: `${backend}${original.pathname}${original.search}`,
      });
      if (["/api/v1/settings", "/api/v1/auth/preferences"].includes(original.pathname)) {
        await route.fulfill({ response, json: { ...(await response.json()), theme: "dark" } });
      } else await route.fulfill({ response });
    });
    const narrowPage = await narrowContext.newPage();
    await narrowPage.goto(`${frontend}/projects/${project.id}/changes?change=${proposed.id}`);
    await narrowPage.getByRole("button", { name: "编辑待采用版本", exact: true }).click();
    await expect(narrowPage.getByRole("textbox", { name: "编辑待采用正文" })).toBeVisible();
    expect(
      await narrowPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    ).toBe(true);
    await narrowPage.screenshot({ path: "../tmp/pending-review-narrow-dark.png", fullPage: true });
  } finally {
    await narrowContext.close();
  }

  await page.getByRole("button", { name: "编辑待采用版本", exact: true }).click();
  await editor.fill("未保存的本地修改");
  const remote = await request.patch(`${root}/${proposed.id}`, {
    data: {
      expected_updated_at: saved.updated_at,
      patch: { body: "模型继续修订的版本" },
    },
  });
  expect(remote.status()).toBe(200);
  await page.getByRole("button", { name: "保存待审", exact: true }).click();
  await expect(
    page.getByText("提案已被修订或处理。本地编辑已保留", { exact: false }),
  ).toBeVisible();
  await expect(editor).toHaveValue("未保存的本地修改");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.reload();
  await expect(panes.last()).toContainText("模型继续修订的版本");
  await page.getByRole("button", { name: "采用", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "采用", exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${root}/${proposed.id}`)).json()).status)
    .toBe("applied");
});
