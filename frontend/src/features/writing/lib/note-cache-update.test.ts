import { describe, expect, it } from "vitest";

import type { NoteCategoryItem, NoteListItem, NoteTreeResponse } from "@/lib/note.types";

import { applyToNote } from "./note-cache-update";

const note = (id: string): NoteListItem => ({
  id,
  projectId: "p",
  categoryId: null,
  title: id,
  documentType: "note",
  order: 0,
  isLocked: false,
  agentVisibility: "all",
  createdAt: "",
  updatedAt: "",
});
const folder = (id: string): NoteCategoryItem => ({
  id,
  projectId: "p",
  parentId: null,
  title: id,
  documentType: "note",
  order: 0,
  createdAt: "",
  updatedAt: "",
  categories: [],
  notes: [note(id + "-1"), note(id + "-2")],
});
const tree = (): NoteTreeResponse => ({
  rootNotes: [note("root")],
  categories: [folder("a"), folder("b")],
  totalNotes: 5,
});

describe("note cache structural sharing", () => {
  it("copies only the affected folder, its list and target note", () => {
    const before = tree();
    const next = applyToNote(before, "a-1", (note) => ({ ...note, agentVisibility: "none" }));
    expect(next).not.toBe(before);
    expect(next.rootNotes).toBe(before.rootNotes);
    expect(next.categories).not.toBe(before.categories);
    expect(next.categories[0]).not.toBe(before.categories[0]);
    expect(next.categories[0]!.notes[0]!.agentVisibility).toBe("none");
    expect(before.categories[0]!.notes[0]!.agentVisibility).toBe("all");
    expect(next.categories[0]!.notes[1]).toBe(before.categories[0]!.notes[1]);
    expect(next.categories[0]!.categories).toBe(before.categories[0]!.categories);
    expect(next.categories[1]).toBe(before.categories[1]);
  });
  it("preserves folders for root updates and protects the old note from mutations", () => {
    const before = tree();
    const next = applyToNote(before, "root", (note) => {
      note.isLocked = true;
      return note;
    });
    expect(next.categories).toBe(before.categories);
    expect(next.rootNotes).not.toBe(before.rootNotes);
    expect(next.rootNotes[0]!.isLocked).toBe(true);
    expect(before.rootNotes[0]!.isLocked).toBe(false);
  });
  it("returns the original tree when the target does not exist", () => {
    const before = tree();
    expect(
      applyToNote(before, "missing", () => {
        throw Error("must not run");
      }),
    ).toBe(before);
  });
});
