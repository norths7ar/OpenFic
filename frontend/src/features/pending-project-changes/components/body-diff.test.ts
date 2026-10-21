import { describe, expect, it } from "vitest";

import { compareBodyBlocks } from "./body-diff";

describe("review block comparison", () => {
  it("keeps inserted paragraphs and deleted endings distinct among modified blocks", () => {
    const diff = compareBodyBlocks(
      "old paragraph\n\n- old list\n\nold end",
      "new paragraph\n\ninserted\n\n- new list",
    );
    expect(diff.before.filter((change) => change !== "unchanged")).toEqual([
      "changed",
      "changed",
      "removed",
    ]);
    expect(diff.after.filter((change) => change !== "unchanged")).toEqual([
      "changed",
      "added",
      "changed",
    ]);
  });
  it("marks replacements without marking the following paragraphs", () => {
    const diff = compareBodyBlocks("old\n\nend", "new\n\nend");
    expect(diff.before).toEqual(["changed", "unchanged", "unchanged"]);
    expect(diff.after).toEqual(["changed", "unchanged", "unchanged"]);
  });
  it("keeps repeated unchanged paragraphs anchored", () => {
    const diff = compareBodyBlocks("same\n\nsame\n\nend", "same\n\nnew\n\nsame\n\nend");
    expect(diff.before.every((change) => change === "unchanged")).toBe(true);
    expect(diff.after.filter((change) => change === "added")).toHaveLength(1);
  });
});
