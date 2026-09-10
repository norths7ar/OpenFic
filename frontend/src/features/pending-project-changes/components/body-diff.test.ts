import { parseMarkdownIntoBlocks } from "streamdown";
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
  it("anchors unchanged paragraphs around an insertion", () => {
    const diff = compareBodyBlocks("first\n\nlast", "first\n\nnew\n\nlast");
    expect(diff.before).toEqual(["unchanged", "unchanged", "unchanged"]);
    expect(diff.after).toEqual(["unchanged", "unchanged", "added", "unchanged", "unchanged"]);
  });
  it("marks replacements without marking the following paragraphs", () => {
    const diff = compareBodyBlocks("old\n\nend", "new\n\nend");
    expect(diff.before).toEqual(["changed", "unchanged", "unchanged"]);
    expect(diff.after).toEqual(["changed", "unchanged", "unchanged"]);
  });
  it("marks creation and deletion", () => {
    expect(compareBodyBlocks("", "new")).toEqual({ before: [], after: ["added"] });
    expect(compareBodyBlocks("old", "")).toEqual({ before: ["removed"], after: [] });
  });
  it("retains multiline lists, tables and fenced code as renderer blocks", () => {
    for (const block of [
      "- one\n- two",
      "| A |\n| --- |\n| B |",
      "```text\nfirst\n\nsecond\n```",
      "> quote\n> continued",
    ]) {
      expect(parseMarkdownIntoBlocks(block)).toHaveLength(1);
      expect(compareBodyBlocks("", block).after).toEqual(["added"]);
    }
  });
  it("keeps repeated unchanged paragraphs anchored", () => {
    const diff = compareBodyBlocks("same\n\nsame\n\nend", "same\n\nnew\n\nsame\n\nend");
    expect(diff.before.every((change) => change === "unchanged")).toBe(true);
    expect(diff.after.filter((change) => change === "added")).toHaveLength(1);
  });
});
