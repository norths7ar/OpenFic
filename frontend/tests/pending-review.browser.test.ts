// Run from frontend: node --test tests/pending-review.browser.test.ts
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import { chromium, expect, type Browser, type Page } from "@playwright/test";
import react from "@vitejs/plugin-react";
import { createServer, type InlineConfig, type Plugin, type ViteDevServer } from "vite-plus";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const scratch = fileURLToPath(
  new URL("../../tmp/gap-tests-validation/frontend-review/", import.meta.url),
);
let server: ViteDevServer;
let browser: Browser;
let origin: string;

before(async () => {
  await mkdir(scratch, { recursive: true });
  // Playwright's temporary browser profile also stays in the validation directory.
  process.env.TEMP = scratch;
  process.env.TMP = scratch;
  process.env.TMPDIR = scratch;
  const config: InlineConfig = {
    configFile: false,
    root: frontend,
    envDir: scratch,
    cacheDir: `${scratch}/vite-cache`,
    optimizeDeps: { entries: ["tests/pending-review-harness.tsx"] },
    resolve: { alias: { "@": `${frontend}/src` } },
    plugins: [
      ...(react() as unknown as Plugin[]),
      {
        name: "isolated-review-harness",
        configureServer(devServer) {
          devServer.middlewares.use(async (request, response, next) => {
            if (request.url?.split("?")[0] !== "/gap-review") return next();
            const html = await devServer.transformIndexHtml(
              "/gap-review",
              '<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root"></div><script type="module" src="/tests/pending-review-harness.tsx"></script></body></html>',
            );
            response.setHeader("Content-Type", "text/html; charset=utf-8");
            response.end(html);
          });
        },
      },
    ],
    // No repository config or proxy: production port/data cannot be reached.
    server: { host: "127.0.0.1", port: 0, hmr: false },
  };
  server = await createServer(config);
  await server.listen();
  origin = server.resolvedUrls!.local[0].replace(/\/$/, "");
  browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    downloadsPath: scratch,
    tracesDir: scratch,
  });
});

after(async () => {
  await browser?.close();
  await server?.close();
});

async function isolatedPage() {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(60000);
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    return url.origin === origin && !url.pathname.startsWith("/api/")
      ? route.continue()
      : route.abort();
  });
  return page;
}

async function compare(page: Page, before: string, after: string) {
  await page.goto(`${origin}/gap-review?${new URLSearchParams({ before, after })}`);
  await expect(page.getByTestId("after").locator(".streaming-markdown")).toBeVisible();
}

async function expectLinkDestination(page: Page, side: string, destination: string) {
  // Production link safety renders a button, then displays the complete URL.
  await page.getByTestId(side).getByRole("button", { name: "案卷", exact: true }).click();
  await expect(page.locator('[data-streamdown="link-safety-dialog-url"]')).toHaveText(destination);
  await page.getByRole("button", { name: "Close", exact: true }).click();
}

// Protects: readers see only the replaced characters highlighted while bold, links and list structure remain usable.
test("character review highlights 戒律司 → 飞瑶 without damaging Markdown", async () => {
  const page = await isolatedPage();
  try {
    await compare(
      page,
      "请**通知戒律司**，查阅[案卷](https://example.invalid/archive)。\n\n- 保留条目\n- 通知戒律司",
      "请**通知飞瑶**，查阅[案卷](https://example.invalid/archive)。\n\n- 保留条目\n- 通知飞瑶",
    );
    for (const [side, changed, full] of [
      ["before", "戒律司", "通知戒律司"],
      ["after", "飞瑶", "通知飞瑶"],
    ]) {
      const view = page.getByTestId(side);
      await expect(view.locator("mark")).toHaveText([changed, changed]);
      await expect(view.locator(`mark.pending-body-character--${side}`)).toHaveCount(2);
      const bold = view.locator('[data-streamdown="strong"]');
      await expect(bold).toHaveText(full);
      await expect(bold).toHaveCSS("font-weight", "700");
      await expectLinkDestination(page, side, "https://example.invalid/archive");
      await expect(view.locator("ul > li")).toHaveText(["保留条目", full]);
      await expect(view.locator(".pending-body-block--changed")).toHaveCount(2);
    }
  } finally {
    await page.close();
  }
});

// Protects: formatting-only and invisible link-destination edits still have a visible changed-block signal.
test("review reports format and link-address changes even with identical visible text", async () => {
  const page = await isolatedPage();
  try {
    await compare(
      page,
      "通知飞瑶\n\n[案卷](https://example.invalid/old)",
      "**通知飞瑶**\n\n[案卷](https://example.invalid/new)",
    );
    for (const side of ["before", "after"]) {
      const view = page.getByTestId(side);
      await expect(view.locator(".pending-body-block--changed")).toHaveCount(2);
      await expect(view.locator(".pending-body-block-label")).toHaveText(["Modified", "Modified"]);
      await expect(view.locator("mark")).toHaveCount(0);
    }
    await expect(page.getByTestId("before").locator('[data-streamdown="strong"]')).toHaveCount(0);
    const bold = page.getByTestId("after").locator('[data-streamdown="strong"]');
    await expect(bold).toHaveText("通知飞瑶");
    await expect(bold).toHaveCSS("font-weight", "700");
    await expectLinkDestination(page, "before", "https://example.invalid/old");
    await expectLinkDestination(page, "after", "https://example.invalid/new");
  } finally {
    await page.close();
  }
});

// Protects: refresh/409 cannot erase typed edits, and browsing history cannot write or replace the latest proposal.
test("real panel preserves unsaved input across refresh/conflict and history is read-only", async () => {
  const page = await isolatedPage();
  const snapshot = { title: "案卷", body: "正式正文", agent_visibility: "always" };
  const oldRevision = {
    id: "revision-1",
    change_id: "change-1",
    after: { ...snapshot, body: "历史建议正文" },
    source: "ai",
    source_task_id: null,
    source_message_id: null,
    model_id: null,
    created_at: "2026-10-20T00:00:00Z",
  };
  const headRevision = {
    ...oldRevision,
    id: "revision-2",
    after: { ...snapshot, body: "最新建议正文" },
    created_at: "2026-10-21T00:00:00Z",
  };
  const concurrentRevision = {
    ...headRevision,
    id: "revision-3",
    after: { ...snapshot, body: "其他人更新后的建议" },
    created_at: "2026-10-21T01:00:00Z",
  };
  const revisions = [oldRevision, headRevision];
  const change = {
    id: "change-1",
    project_id: "gap-project",
    target_type: "note",
    target_id: "note-1",
    operation: "update",
    before: snapshot,
    after: headRevision.after,
    current: snapshot,
    base_hash: "base",
    current_hash: "current",
    current_revision_id: headRevision.id,
    applied_revision_id: null,
    source_task_id: null,
    source_message_id: null,
    model_id: null,
    status: "pending",
    is_applicable: true,
    applicability_reason: null,
    applied_at: null,
    created_at: headRevision.created_at,
    updated_at: headRevision.created_at,
  };
  const writes: { method: string; body: unknown }[] = [];
  let detailReads = 0;
  await page.route(`${origin}/api/v1/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") {
      writes.push({ method: request.method(), body: request.postDataJSON() });
      await route.fulfill({ status: 409, json: { detail: "Proposal changed" } });
    } else if (path.endsWith("/agent-visibility")) {
      await route.fulfill({
        json: {
          default: "always",
          states: [
            {
              value: "always",
              label: "Always",
              description: "",
              export_marker: "",
              scopes: ["note"],
            },
          ],
        },
      });
    } else if (path.endsWith("/count")) {
      await route.fulfill({ json: { count: 1 } });
    } else if (path.endsWith("/revisions/revision-1")) {
      await route.fulfill({ json: oldRevision });
    } else if (path.endsWith("/revisions")) {
      await route.fulfill({ json: revisions });
    } else if (path.endsWith("/change-1")) {
      detailReads++;
      await route.fulfill({ json: change });
    } else if (path.endsWith("/pending-changes")) {
      await route.fulfill({ json: [change] });
    } else {
      await route.abort();
    }
  });
  try {
    await page.goto(`${origin}/gap-review?panel=1`);
    await page.getByRole("button", { name: "Edit proposed version", exact: true }).click();
    const title = page.getByRole("textbox", { name: "Title", exact: true });
    const body = page.getByRole("textbox", { name: "Edit proposed body", exact: true });
    await title.fill("用户未保存标题");
    await body.fill("用户未保存正文\n**通知飞瑶**");
    const initialReads = detailReads;
    // Simulate a new server head through the HTTP boundary, not component state.
    revisions.push(concurrentRevision);
    change.updated_at = concurrentRevision.created_at;
    change.current_revision_id = concurrentRevision.id;
    change.after = concurrentRevision.after;
    await page
      .getByRole("button", { name: "Refresh current content and history", exact: true })
      .click();
    await expect.poll(() => detailReads).toBeGreaterThan(initialReads);
    await expect(title).toHaveValue("用户未保存标题");
    await expect(body).toHaveValue("用户未保存正文\n**通知飞瑶**");
    await expect(
      page.getByRole("combobox", { name: "Proposal version", exact: true }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Save draft", exact: true }).click();
    await expect.poll(() => writes.length).toBe(1);
    await expect.poll(() => detailReads).toBeGreaterThan(initialReads + 1);
    await expect(body).toBeEnabled();
    await expect(title).toHaveValue("用户未保存标题");
    await expect(body).toHaveValue("用户未保存正文\n**通知飞瑶**");
    assert.deepEqual(writes, [
      {
        method: "PATCH",
        body: {
          expected_updated_at: headRevision.created_at,
          patch: { title: "用户未保存标题", body: "用户未保存正文\n**通知飞瑶**" },
        },
      },
    ]);
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    const proposed = page.locator(".pending-project-changes-body-version").nth(1);
    await page.getByRole("combobox", { name: "Proposal version", exact: true }).click();
    await page.getByRole("option", { name: /^Version 1/ }).click();
    await expect(proposed).toContainText("历史建议正文");
    assert.equal(writes.length, 1, "Selecting history must not issue a write");
    await page.getByRole("combobox", { name: "Proposal version", exact: true }).click();
    await page.getByRole("option", { name: /^Latest version/ }).click();
    await expect(proposed).toContainText("其他人更新后的建议");
    assert.equal(writes.length, 1, "Returning to latest must not rewrite the proposal");
  } finally {
    await page.close();
  }
});
