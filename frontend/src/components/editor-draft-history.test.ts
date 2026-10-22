import { describe, expect, it } from "vitest";

import { EditorDraftHistory } from "./editor-draft-history";

describe("shared source and visual draft history", () => {
  it("keeps the exact original Markdown when undoing across editing modes", () => {
    const original = "# 标题\n\n<!-- 保留注释 -->\n\n*原有写法*\n";
    const history = new EditorDraftHistory(original);
    history.record(`${original}源码修改`, 1000);
    history.breakGroup(); // Switching to visual mode must not create an edit.
    expect(history.content).toBe(`${original}源码修改`);
    history.record("# 标题\n\n可视化修改", 1100);
    expect(history.undo()).toBe(`${original}源码修改`);
    expect(history.undo()).toBe(original);
    expect(history.canUndo).toBe(false);
    expect(history.redo()).toBe(`${original}源码修改`);
  });
});
