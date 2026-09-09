import { beforeEach, describe, expect, it, vi } from "vitest";

const records = vi.hoisted(
  () => new Map<string, { tabs: unknown[]; activeTabId: string | null }>(),
);
vi.mock("@/lib/local-db", () => ({
  getProjectTabs: vi.fn(async (id: string) => records.get(id)),
  setProjectTabs: vi.fn(async (id: string, tabs: unknown[], activeTabId: string | null) => {
    records.set(id, { tabs, activeTabId });
  }),
}));

import { getProjectTabs } from "@/lib/local-db";

import { createTabsStore } from "./use-tabs-store";

describe("workspace tabs", () => {
  beforeEach(() => records.clear());

  it("restores explicitly empty workspaces without manufacturing a tab", async () => {
    const store = createTabsStore();
    await store.getState().setCurrentProject("project:notes");
    store.getState().openTab("one", "One", "note");
    store.getState().closeTab("note:one");
    const restored = createTabsStore();
    await restored.getState().setCurrentProject("project:notes");
    expect(restored.getState().tabs).toEqual([]);
    expect(restored.getState().activeTabId).toBeNull();
  });

  it("keeps projects/pages isolated and restores active tab and scroll", async () => {
    const store = createTabsStore();
    await store.getState().setCurrentProject("project:notes");
    store.getState().openTab("one", "One", "note");
    store.getState().openTab("two", "Two", "note");
    store.getState().openTab("one", "One", "note");
    store.getState().updateTabScrollPosition("note:one", 240);
    expect(store.getState().tabs).toHaveLength(2);
    await store.getState().setCurrentProject("project:outline");
    expect(store.getState().tabs).toEqual([]);
    await store.getState().setCurrentProject("project:notes");
    expect(store.getState().activeTabId).toBe("note:one");
    expect(store.getState().tabs[0].scrollTop).toBe(240);
  });

  it("removes deleted references and legacy empty tabs on restore", async () => {
    records.set("project", {
      tabs: [{ id: "empty:old", refId: null, title: "", type: "chapter" }],
      activeTabId: "empty:old",
    });
    const store = createTabsStore();
    await store.getState().setCurrentProject("project");
    expect(store.getState().tabs).toEqual([]);
    store.getState().openTab("one", "One");
    store.getState().syncTabsWithChapters([]);
    expect(store.getState().activeTabId).toBeNull();
  });

  it("ignores an older pending restore after switching projects away and back", async () => {
    let finishOld!: (value: undefined) => void;
    vi.mocked(getProjectTabs).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve;
        }),
    );
    const store = createTabsStore();
    const oldLoad = store.getState().setCurrentProject("a");
    await store.getState().setCurrentProject("b");
    await store.getState().setCurrentProject("a");
    store.getState().openTab("latest", "Latest");
    finishOld(undefined);
    await oldLoad;
    expect(store.getState().activeTabId).toBe("chapter:latest");
  });

  it("activates a remaining tab when the active reference is deleted", async () => {
    const store = createTabsStore();
    await store.getState().setCurrentProject("a");
    store.getState().openTab("one", "One", "note");
    store.getState().openTab("two", "Two", "note");
    store.getState().removeTabsByReference("note", "two");
    expect(store.getState().activeTabId).toBe("note:one");
    store.getState().syncTabs([{ id: "one", title: "Renamed" }], "note");
    expect(store.getState().tabs[0].title).toBe("Renamed");
  });
});
