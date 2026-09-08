import { describe, expect, it } from "vitest";

import { resolveWritingWorkingCopy } from "./writing-working-copy";

const remote = (title = "saved", content = "server", updatedAt = "2026-09-08T00:00:00Z") => ({
  title,
  content,
  updatedAt,
});

describe("writing working-copy recovery", () => {
  it("recovers a local draft when the remote content still matches its base", () => {
    const resolved = resolveWritingWorkingCopy(remote("saved", "server", "2026-09-08T01:00:00Z"), {
      title: "local",
      content: "draft",
      baseTitle: "saved",
      baseContent: "server",
      baseUpdatedAt: "2026-09-08T00:00:00Z",
      updatedAt: new Date(),
    });
    expect(resolved.draft).toEqual({ title: "local", content: "draft" });
    expect(resolved.conflict).toBeUndefined();
  });

  it("keeps both versions when remote content changed", () => {
    const resolved = resolveWritingWorkingCopy(remote("saved", "other"), {
      title: "local",
      content: "draft",
      baseTitle: "saved",
      baseContent: "server",
      baseUpdatedAt: "2026-09-07T00:00:00Z",
      updatedAt: new Date(),
    });
    expect(resolved.conflict?.local.content).toBe("draft");
    expect(resolved.conflict?.remote.content).toBe("other");
  });

  it("adopts the remote version when the local draft still equals its content base", () => {
    const resolved = resolveWritingWorkingCopy(remote("saved", "remote", "2026-09-08T01:00:00Z"), {
      title: "saved",
      content: "server",
      baseTitle: "saved",
      baseContent: "server",
      baseUpdatedAt: "2026-09-08T00:00:00Z",
      updatedAt: new Date(),
    });

    expect(resolved).toEqual({
      draft: { title: "saved", content: "remote" },
      shouldDelete: true,
    });
  });

  it("treats a changed content base as a conflict even when timestamps match", () => {
    const resolved = resolveWritingWorkingCopy(remote("saved", "remote"), {
      title: "local",
      content: "draft",
      baseTitle: "saved",
      baseContent: "server",
      baseUpdatedAt: "2026-09-08T00:00:00Z",
      updatedAt: new Date(),
    });

    expect(resolved.conflict).toBeDefined();
  });
});
