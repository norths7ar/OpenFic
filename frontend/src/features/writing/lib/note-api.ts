import { apiClient } from "@/lib/api-transport";
import type {
  DocumentType,
  Note,
  NoteCategory,
  NoteCategoryCreate,
  NoteCategoryItem,
  NoteCategoryUpdate,
  NoteCreate,
  NoteItemMove,
  NoteItemReorder,
  NoteItemsMixedReorder,
  NoteListItem,
  NoteMoveResult,
  NoteTreeResponse,
  NoteUpdate,
} from "@/lib/note.types";

function transformNote(raw: Record<string, unknown>): Note {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    categoryId: (raw.category_id as string | null | undefined) ?? null,
    title: raw.title as string,
    documentType: (raw.scope ?? raw.document_type) as DocumentType,
    content: raw.content as string,
    order: raw.order as number,
    isLocked: raw.is_locked as boolean,
    isHidden: raw.is_hidden as boolean,
    isWritingVisible: raw.is_writing_visible as boolean,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformNoteListItem(raw: Record<string, unknown>): NoteListItem {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    categoryId: (raw.category_id as string | null | undefined) ?? null,
    title: raw.title as string,
    documentType: (raw.scope ?? raw.document_type) as DocumentType,
    order: raw.order as number,
    isLocked: raw.is_locked as boolean,
    isHidden: raw.is_hidden as boolean,
    isWritingVisible: raw.is_writing_visible as boolean,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformNoteCategory(raw: Record<string, unknown>): NoteCategory {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    description: (raw.description as string | null) ?? null,
    parentId: (raw.parent_id as string | null | undefined) ?? null,
    title: raw.title as string,
    documentType: (raw.scope ?? raw.document_type) as DocumentType,
    order: raw.order as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformNoteCategoryItem(raw: Record<string, unknown>): NoteCategoryItem {
  return {
    ...transformNoteCategory(raw),
    categories: ((raw.categories as Record<string, unknown>[]) ?? []).map(
      transformNoteCategoryItem,
    ),
    notes: ((raw.notes as Record<string, unknown>[]) ?? []).map(transformNoteListItem),
  };
}

function transformNoteTree(raw: Record<string, unknown>): NoteTreeResponse {
  return {
    categories: ((raw.categories as Record<string, unknown>[]) ?? []).map(
      transformNoteCategoryItem,
    ),
    rootNotes: ((raw.root_notes as Record<string, unknown>[]) ?? []).map(transformNoteListItem),
    totalNotes: raw.total_notes as number,
  };
}

function transformNoteMoveResult(raw: Record<string, unknown>): NoteMoveResult {
  return {
    kind: raw.kind as "category" | "note",
    note: raw.note ? transformNote(raw.note as Record<string, unknown>) : undefined,
    category: raw.category
      ? transformNoteCategory(raw.category as Record<string, unknown>)
      : undefined,
  };
}

export async function fetchNoteTree(
  projectId: string,
  documentType: DocumentType = "note",
): Promise<NoteTreeResponse> {
  const response = await apiClient.get(`/projects/${projectId}/notes`, {
    params: { document_type: documentType },
  });
  return transformNoteTree(response.data);
}

export async function reorderNoteItems(projectId: string, data: NoteItemReorder): Promise<number> {
  const response = await apiClient.post(`/projects/${projectId}/note-items/reorder`, {
    kind: data.kind,
    parent_id: data.parentId,
    ordered_ids: data.orderedIds,
    document_type: data.documentType ?? "note",
  });
  return response.data.updated_count as number;
}

export async function reorderMixedNoteItems(
  projectId: string,
  data: NoteItemsMixedReorder,
): Promise<number> {
  const response = await apiClient.post(`/projects/${projectId}/note-items/reorder-mixed`, {
    parent_id: data.parentId,
    ordered_items: data.orderedItems,
    document_type: data.documentType ?? "note",
  });
  return response.data.updated_count as number;
}

export async function fetchNote(noteId: string): Promise<Note> {
  const response = await apiClient.get(`/notes/${noteId}`);
  return transformNote(response.data);
}

export async function createNote(projectId: string, data: NoteCreate): Promise<Note> {
  const response = await apiClient.post(`/projects/${projectId}/notes`, {
    category_id: data.categoryId,
    title: data.title,
    content: data.content,
    document_type: data.documentType ?? "note",
  });
  return transformNote(response.data);
}

export async function updateNote(noteId: string, data: NoteUpdate): Promise<Note> {
  const response = await apiClient.patch(`/notes/${noteId}`, {
    title: data.title,
    content: data.content,
    is_writing_visible: data.isWritingVisible,
    is_hidden: data.isHidden,
  });
  return transformNote(response.data);
}

export async function deleteNote(noteId: string): Promise<void> {
  await apiClient.delete(`/notes/${noteId}`);
}

export async function toggleNoteLock(noteId: string, isLocked: boolean): Promise<Note> {
  const response = await apiClient.patch(`/notes/${noteId}/lock`, {
    is_locked: isLocked,
  });
  return transformNote(response.data);
}

export async function toggleNoteHidden(noteId: string, isHidden: boolean): Promise<Note> {
  const response = await apiClient.patch(`/notes/${noteId}/hidden`, {
    is_hidden: isHidden,
  });
  return transformNote(response.data);
}

export async function createNoteCategory(
  projectId: string,
  data: NoteCategoryCreate,
): Promise<NoteCategory> {
  const response = await apiClient.post(`/projects/${projectId}/folders`, {
    title: data.title,
    scope: data.documentType ?? "note",
  });
  return transformNoteCategory(response.data);
}

export async function updateNoteCategory(
  categoryId: string,
  data: NoteCategoryUpdate,
): Promise<NoteCategory> {
  const response = await apiClient.patch(`/folders/${categoryId}`, {
    title: data.title,
    description: data.description,
  });
  return transformNoteCategory(response.data);
}

export async function deleteNoteCategory(categoryId: string): Promise<void> {
  await apiClient.delete(`/folders/${categoryId}`);
}

export async function moveNoteItem(data: NoteItemMove): Promise<NoteMoveResult> {
  const response = await apiClient.post("/note-items/move", {
    kind: data.kind,
    item_id: data.itemId,
    target_category_id: data.targetCategoryId,
  });
  return transformNoteMoveResult(response.data);
}
