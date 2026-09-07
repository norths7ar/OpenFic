import { describe, expect, it } from "vitest";

import { projectNavGroups } from "./project-nav-groups";

describe("project navigation root semantics", () => {
  const root = { id: "root-item", folderId: null };
  const child = { id: "child", folderId: "a" };
  const folder = { id: "a", title: "same" };
  const getFolder = (item: { folderId: string | null }) => item.folderId;

  it("renders roots without a header even without real folders", () => {
    expect(projectNavGroups([], [root], getFolder)).toEqual([
      { folder: null, items: [root], showHeader: false },
    ]);
  });
  it("places roots before real folders without a root header", () => {
    expect(projectNavGroups([folder], [child, root], getFolder)).toEqual([
      { folder: null, items: [root], showHeader: false },
      { folder, items: [child], showHeader: true },
    ]);
  });
  it("does not leave an empty root group", () => {
    expect(projectNavGroups([folder], [child], getFolder)).toHaveLength(1);
    expect(projectNavGroups([], [], getFolder)).toEqual([]);
  });
  it("keeps same-name folders distinct by ID", () => {
    const other = { id: "b", title: "same" };
    const groups = projectNavGroups([folder, other], [child], getFolder);
    expect(groups.map((group) => group.folder?.id)).toEqual(["a", "b"]);
    expect(groups.map((group) => group.items.length)).toEqual([1, 0]);
  });
});
