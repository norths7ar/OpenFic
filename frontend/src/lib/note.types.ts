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
  isHidden: boolean;
  isWritingVisible: boolean;
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
  isHidden: boolean;
  isWritingVisible: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface NoteCategory {
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
  isWritingVisible?: boolean;
}

export interface NoteCategoryCreate {
  parentId?: string | null;
  title: string;
  documentType?: DocumentType;
}

export interface NoteCategoryUpdate {
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

export interface NoteMoveResult {
  kind: "category" | "note";
  note?: Note;
  category?: NoteCategory;
}
