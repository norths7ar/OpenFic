export type DocumentType = "note" | "outline";

export interface Note {
  id: string;
  projectId: string;
  categoryId: string | null;
  title: string;
  documentType: DocumentType;
  content: string;
  order: number;
  isLocked: boolean;
  agentVisibility: string;
  createdAt: string;
  updatedAt: string;
}

export interface NoteListItem {
  id: string;
  projectId: string;
  categoryId: string | null;
  title: string;
  documentType: DocumentType;
  order: number;
  isLocked: boolean;
  agentVisibility: string;
  createdAt: string;
  updatedAt: string;
}

export interface NoteCategory {
  description?: string | null;
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  documentType: DocumentType;
  order: number;
  createdAt: string;
  updatedAt: string;
}

export interface NoteCategoryItem extends NoteCategory {
  categories: NoteCategoryItem[];
  notes: NoteListItem[];
}

export interface NoteTreeResponse {
  categories: NoteCategoryItem[];
  rootNotes: NoteListItem[];
  totalNotes: number;
}

export interface NoteCreate {
  categoryId?: string | null;
  title: string;
  content?: string;
  documentType?: DocumentType;
}

export interface NoteUpdate {
  title?: string;
  content?: string;
  agentVisibility?: string;
}

export interface NoteCategoryCreate {
  parentId?: string | null;
  title: string;
  documentType?: DocumentType;
}

export interface NoteCategoryUpdate {
  description?: string | null;
  title?: string;
}

export interface NoteItemMove {
  kind: "category" | "note";
  itemId: string;
  targetCategoryId?: string | null;
}

export interface NoteItemReorder {
  kind: "category" | "note";
  parentId: string | null;
  orderedIds: string[];
  documentType?: DocumentType;
}

export interface NoteOrderedItem {
  kind: "category" | "note";
  id: string;
}

export interface NoteItemsMixedReorder {
  parentId: string | null;
  orderedItems: NoteOrderedItem[];
  documentType?: DocumentType;
}

export interface NoteMoveResult {
  kind: "category" | "note";
  note?: Note;
  category?: NoteCategory;
}
