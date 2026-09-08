import { describe, expect, it } from "vitest";

import { getReorderedChapterIds } from "./grouped-volume-list-model";

describe("chapter manual order", () => {
  const chapters = [
    { id: "b", order: 2 },
    { id: "a", order: 1 },
    { id: "c", order: 3 },
  ];
  it("reorders according to chapter sequence without mutating the source", () => {
    expect(getReorderedChapterIds(chapters, "c", "a")).toEqual(["c", "a", "b"]);
    expect(chapters.map((chapter) => chapter.id)).toEqual(["b", "a", "c"]);
  });
  it("ignores unchanged drops", () => {
    expect(getReorderedChapterIds(chapters, "a", "a")).toBeNull();
  });
  it("never assigns a chapter to another volume", () => {
    expect(getReorderedChapterIds(chapters, "a", "other-volume-chapter")).toBeNull();
    expect(getReorderedChapterIds(chapters, "other-volume-chapter", "a")).toBeNull();
  });
});
