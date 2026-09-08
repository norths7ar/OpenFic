import { beforeEach, describe, expect, it, vi } from "vitest";

const localDb = vi.hoisted(() => ({
  deleteWritingWorkingCopyIfUpdatedAt: vi.fn(),
  getWritingWorkingCopy: vi.fn(),
}));

vi.mock("@/lib/local-db", () => ({
  ...localDb,
}));

import { loadWritingEditorEntity } from "./use-writing-editor-entity";

const entity = {
  id: "chapter-1",
  title: "saved title",
  content: "saved content",
  updatedAt: "2026-09-08T01:00:00Z",
};

describe("loadWritingEditorEntity", () => {
  beforeEach(() => {
    localDb.deleteWritingWorkingCopyIfUpdatedAt.mockReset();
    localDb.getWritingWorkingCopy.mockReset();
  });

  it("returns the working copy's original content base instead of the fetched remote version", async () => {
    localDb.getWritingWorkingCopy.mockResolvedValue({
      entityId: entity.id,
      type: "chapter",
      title: "local title",
      content: "local content",
      baseUpdatedAt: "2026-09-08T00:00:00Z",
      baseTitle: "original title",
      baseContent: "original content",
      updatedAt: new Date("2026-09-08T02:00:00Z"),
    });

    const result = await loadWritingEditorEntity("chapter", entity.id, async () => entity);

    expect(result.baseUpdatedAt).toBe("2026-09-08T00:00:00Z");
    expect(result.baseDraft).toEqual({ title: "original title", content: "original content" });
  });

  it("keeps a legacy working copy's content base unknown", async () => {
    localDb.getWritingWorkingCopy.mockResolvedValue({
      entityId: entity.id,
      type: "chapter",
      title: "local title",
      content: "local content",
      baseUpdatedAt: "2026-09-08T00:00:00Z",
      updatedAt: new Date("2026-09-08T02:00:00Z"),
    });

    const result = await loadWritingEditorEntity("chapter", entity.id, async () => entity);

    expect(result.baseDraft).toBeUndefined();
  });
});
