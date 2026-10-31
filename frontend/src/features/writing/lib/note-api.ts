import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
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

function transformNote(raw: schemas.NoteResponse & { scope?: DocumentType }): Note {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    categoryId: (raw.category_id as string | null | undefined) ?? null,
    title: raw.title as string,
    documentType: (raw.scope ?? raw.document_type) as DocumentType,
    content: raw.content as string,
    order: raw.order as number,
    isLocked: raw.is_locked as boolean,
    agentVisibility: raw.agent_visibility,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformNoteListItem(raw: schemas.NoteListItem & { scope?: DocumentType }): NoteListItem {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    categoryId: (raw.category_id as string | null | undefined) ?? null,
    title: raw.title as string,
    documentType: (raw.scope ?? raw.document_type) as DocumentType,
    order: raw.order as number,
    isLocked: raw.is_locked as boolean,
    agentVisibility: raw.agent_visibility as string,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformNoteCategory(
  raw:
    | (schemas.NoteCategoryResponse & { scope?: DocumentType })
    | (schemas.ProjectFolderResponse & { document_type?: DocumentType }),
): NoteCategory {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    description: (raw.description as string | null) ?? null,
    parentId: ("parent_id" in raw ? raw.parent_id : null) ?? null,
    title: raw.title as string,
    documentType: (raw.scope ?? raw.document_type) as DocumentType,
    order: raw.order as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformNoteCategoryItem(raw: schemas.NoteCategoryItem): NoteCategoryItem {
  return {
    ...transformNoteCategory(raw),
    categories: (raw.categories ?? []).map(transformNoteCategoryItem),
    notes: (raw.notes ?? []).map(transformNoteListItem),
  };
}

function transformNoteTree(raw: schemas.NoteTreeResponse): NoteTreeResponse {
  return {
    categories: (raw.categories ?? []).map(transformNoteCategoryItem),
    rootNotes: (raw.root_notes ?? []).map(transformNoteListItem),
    totalNotes: raw.total_notes as number,
  };
}

function transformNoteMoveResult(raw: schemas.NoteMoveResult): NoteMoveResult {
  return {
    kind: raw.kind as "category" | "note",
    note: raw.note ? transformNote(raw.note) : undefined,
    category: raw.category ? transformNoteCategory(raw.category) : undefined,
  };
}

export async function fetchNoteTree(
  projectId: string,
  documentType: DocumentType = "note",
): Promise<NoteTreeResponse> {
  const response = await http.listNotesApiV1ProjectsProjectIdNotesGet(projectId, {
    document_type: documentType,
  });
  return transformNoteTree(response.data);
}

export async function reorderNoteItems(projectId: string, data: NoteItemReorder): Promise<number> {
  const response = await http.reorderNoteItemsApiV1ProjectsProjectIdNoteItemsReorderPost(
    projectId,
    {
      kind: data.kind,
      parent_id: data.parentId,
      ordered_ids: data.orderedIds,
      document_type: data.documentType ?? "note",
    },
  );
  return response.data.updated_count as number;
}

export async function reorderMixedNoteItems(
  projectId: string,
  data: NoteItemsMixedReorder,
): Promise<number> {
  const response = await http.reorderMixedNoteItemsApiV1ProjectsProjectIdNoteItemsReorderMixedPost(
    projectId,
    {
      parent_id: data.parentId,
      ordered_items: data.orderedItems,
      document_type: data.documentType ?? "note",
    },
  );
  return response.data.updated_count as number;
}

export async function fetchNote(noteId: string): Promise<Note> {
  const response = await http.getNoteApiV1NotesNoteIdGet(noteId);
  return transformNote(response.data);
}

export async function createNote(projectId: string, data: NoteCreate): Promise<Note> {
  const response = await http.createNoteApiV1ProjectsProjectIdNotesPost(projectId, {
    category_id: data.categoryId,
    title: data.title,
    content: data.content,
    document_type: data.documentType ?? "note",
  });
  return transformNote(response.data);
}

export async function updateNote(noteId: string, data: NoteUpdate): Promise<Note> {
  const contentBase =
    data.baseTitle !== undefined && data.baseContent !== undefined
      ? { base_title: data.baseTitle, base_content: data.baseContent }
      : {};
  const response = await http.updateNoteApiV1NotesNoteIdPatch(noteId, {
    title: data.title,
    content: data.content,
    agent_visibility: data.agentVisibility as schemas.AgentVisibility | undefined,
    base_updated_at: data.baseUpdatedAt,
    ...contentBase,
  });
  return transformNote(response.data);
}

export async function deleteNote(noteId: string): Promise<void> {
  await http.deleteNoteApiV1NotesNoteIdDelete(noteId);
}

export async function toggleNoteLock(noteId: string, isLocked: boolean): Promise<Note> {
  const response = await http.toggleNoteLockApiV1NotesNoteIdLockPatch(noteId, {
    is_locked: isLocked,
  });
  return transformNote(response.data);
}

export async function createNoteCategory(
  projectId: string,
  data: NoteCategoryCreate,
): Promise<NoteCategory> {
  const response = await http.createProjectFolderApiV1ProjectsProjectIdFoldersPost(projectId, {
    title: data.title,
    scope: data.documentType ?? "note",
  });
  return transformNoteCategory(response.data);
}

export async function updateNoteCategory(
  categoryId: string,
  data: NoteCategoryUpdate,
): Promise<NoteCategory> {
  const response = await http.updateProjectFolderApiV1FoldersFolderIdPatch(categoryId, {
    title: data.title,
    description: data.description,
  });
  return transformNoteCategory(response.data);
}

export async function deleteNoteCategory(categoryId: string): Promise<void> {
  await http.deleteProjectFolderApiV1FoldersFolderIdDelete(categoryId);
}

export async function moveNoteItem(data: NoteItemMove): Promise<NoteMoveResult> {
  const response = await http.moveItemApiV1NoteItemsMovePost({
    kind: data.kind,
    item_id: data.itemId,
    target_category_id: data.targetCategoryId,
  });
  return transformNoteMoveResult(response.data);
}
