import type { NoteListItem, NoteTreeResponse } from "@/lib/note.types";

// Folder responses are flat. Preserve every branch unaffected by this note update.
export function applyToNote(
  tree: NoteTreeResponse,
  noteId: string,
  mutator: (note: NoteListItem) => NoteListItem,
): NoteTreeResponse {
  const update = (notes: NoteListItem[]) => {
    const index = notes.findIndex((note) => note.id === noteId);
    if (index < 0) return notes;
    const next = notes.slice();
    next[index] = mutator({ ...notes[index]! });
    return next;
  };
  const rootNotes = update(tree.rootNotes);
  let categories = tree.categories;
  for (const [index, folder] of tree.categories.entries()) {
    const notes = update(folder.notes);
    if (notes === folder.notes) continue;
    if (categories === tree.categories) categories = tree.categories.slice();
    categories[index] = { ...folder, notes };
  }
  return rootNotes === tree.rootNotes && categories === tree.categories
    ? tree
    : { ...tree, rootNotes, categories };
}
