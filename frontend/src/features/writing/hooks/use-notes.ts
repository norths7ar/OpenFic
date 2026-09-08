import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import type {
  Note,
  NoteCreate,
  NoteListItem,
  NoteUpdate,
  NoteCategoryCreate,
  NoteCategoryUpdate,
  NoteItemMove,
  NoteItemReorder,
  NoteItemsMixedReorder,
  NoteTreeResponse,
  NoteCategoryItem,
  DocumentType,
} from "@/lib/note.types";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";

import {
  fetchNoteTree,
  fetchNote,
  createNote,
  updateNote,
  deleteNote,
  toggleNoteLock,
  createNoteCategory,
  updateNoteCategory,
  deleteNoteCategory,
  moveNoteItem,
  reorderMixedNoteItems,
  reorderNoteItems,
} from "../lib/note-api";

// The legacy response envelope is flat; folder IDs are the only association authority.
function cloneTree(tree: NoteTreeResponse): NoteTreeResponse {
  return {
    ...tree,
    rootNotes: tree.rootNotes.map((note) => ({ ...note })),
    categories: tree.categories.map((folder) => ({
      ...folder,
      categories: [],
      notes: folder.notes.map((note) => ({ ...note })),
    })),
  };
}
type NoteMutator = (note: NoteListItem) => NoteListItem;
function applyToNote(
  tree: NoteTreeResponse,
  noteId: string,
  mutator: NoteMutator,
): NoteTreeResponse {
  const next = cloneTree(tree);
  for (const notes of [next.rootNotes, ...next.categories.map((folder) => folder.notes)]) {
    const index = notes.findIndex((note) => note.id === noteId);
    if (index >= 0) notes[index] = mutator(notes[index]!);
  }
  return next;
}
type CategoryMutator = (category: NoteCategoryItem) => NoteCategoryItem;
function applyToCategory(
  tree: NoteTreeResponse,
  categoryId: string,
  mutator: CategoryMutator,
): NoteTreeResponse {
  return {
    ...tree,
    categories: tree.categories.map((folder) =>
      folder.id === categoryId ? mutator(folder) : folder,
    ),
  };
}
function removeNoteFromTree(tree: NoteTreeResponse, noteId: string): NoteTreeResponse {
  const next = cloneTree(tree);
  next.rootNotes = next.rootNotes.filter((note) => note.id !== noteId);
  next.categories = next.categories.map((folder) => ({
    ...folder,
    notes: folder.notes.filter((note) => note.id !== noteId),
  }));
  next.totalNotes = next.rootNotes.length + countCategoryNotes(next.categories);
  return next;
}
function removeCategoryFromTree(tree: NoteTreeResponse, categoryId: string): NoteTreeResponse {
  const next = cloneTree(tree);
  const folder = next.categories.find((folder) => folder.id === categoryId);
  next.categories = next.categories.filter((folder) => folder.id !== categoryId);
  const start = Math.max(0, ...next.rootNotes.map((note) => note.order)) + 1;
  next.rootNotes.push(
    ...(folder?.notes ?? []).map((note, index) => ({
      ...note,
      categoryId: null,
      order: start + index,
    })),
  );
  return next;
}
function findNoteInTree(tree: NoteTreeResponse, noteId: string): NoteListItem | undefined {
  return [...tree.rootNotes, ...tree.categories.flatMap((folder) => folder.notes)].find(
    (note) => note.id === noteId,
  );
}
function moveNoteInTree(
  tree: NoteTreeResponse,
  noteId: string,
  targetCategoryId: string | null,
): NoteTreeResponse {
  const source = findNoteInTree(tree, noteId);
  if (!source) return tree;
  const next = removeNoteFromTree(tree, noteId);
  const target =
    targetCategoryId === null
      ? next.rootNotes
      : next.categories.find((folder) => folder.id === targetCategoryId)?.notes;
  if (!target) return tree;
  target.push({
    ...source,
    categoryId: targetCategoryId,
    order: Math.max(0, ...target.map((note) => note.order)) + 1,
  });
  next.totalNotes = tree.totalNotes;
  return next;
}
function moveCategoryInTree(
  tree: NoteTreeResponse,
  _categoryId: string,
  _targetCategoryId: string | null,
): NoteTreeResponse {
  // Folders have no parent. The compatibility API rejects non-root targets.
  return tree;
}
function countCategoryNotes(folders: NoteCategoryItem[]): number {
  return folders.reduce((sum, folder) => sum + folder.notes.length, 0);
}

export function useNoteTree(projectId: string, documentType: DocumentType = "note") {
  return useQuery({
    queryKey: projectDataQueryKeys.notes.typedTree(projectId, documentType),
    queryFn: () => fetchNoteTree(projectId, documentType),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useNote(noteId: string | null) {
  return useQuery({
    queryKey: projectDataQueryKeys.notes.detail(noteId),
    queryFn: () => fetchNote(noteId!),
    enabled: !!noteId,
    staleTime: 0,
  });
}

export function useCreateNote(projectId: string, documentType: DocumentType = "note") {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (data: NoteCreate) => createNote(projectId, { ...data, documentType }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.notes.tree(projectId, documentType),
      });
      toast.success(t("writing.noteCreated"));
    },
    onError: () => {
      toast.error(t("writing.noteCreateFailed"));
    },
  });
}

export function useUpdateNote(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: ({ noteId, data }: { noteId: string; data: NoteUpdate }) =>
      updateNote(noteId, data),
    onMutate: async ({ noteId, data }) => {
      await queryClient.cancelQueries({
        queryKey: projectDataQueryKeys.notes.tree(projectId),
      });
      const previous = queryClient.getQueryData<NoteTreeResponse>(
        projectDataQueryKeys.notes.tree(projectId),
      );
      if (previous && (data.title !== undefined || data.agentVisibility !== undefined)) {
        queryClient.setQueryData<NoteTreeResponse>(
          projectDataQueryKeys.notes.tree(projectId),
          (tree) => {
            if (!tree) return tree;
            return applyToNote(tree, noteId, (note) => ({
              ...note,
              ...(data.title !== undefined ? { title: data.title } : {}),
              ...(data.agentVisibility !== undefined
                ? { agentVisibility: data.agentVisibility }
                : {}),
            }));
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          projectDataQueryKeys.notes.tree(projectId),
          context.previous,
        );
      }
      toast.error(t("writing.noteRenameFailed"));
    },
    onSuccess: (updatedNote) => {
      queryClient.setQueryData(projectDataQueryKeys.notes.detail(updatedNote.id), updatedNote);
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.notes.tree(updatedNote.projectId),
      });
    },
  });
}

export function useDeleteNote(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (noteId: string) => deleteNote(noteId),
    onMutate: async (noteId) => {
      await queryClient.cancelQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      const previous = queryClient.getQueryData<NoteTreeResponse>(
        projectDataQueryKeys.notes.tree(projectId),
      );
      if (previous) {
        queryClient.setQueryData<NoteTreeResponse>(
          projectDataQueryKeys.notes.tree(projectId),
          (tree) => {
            if (!tree) return tree;
            return removeNoteFromTree(tree, noteId);
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(projectDataQueryKeys.notes.tree(projectId), context.previous);
      }
      toast.error(t("writing.deleteNoteFailed"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      toast.success(t("writing.deleteNoteSuccess"));
    },
  });
}

export function useToggleNoteLock(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: ({ noteId, isLocked }: { noteId: string; isLocked: boolean }) =>
      toggleNoteLock(noteId, isLocked),
    onMutate: async ({ noteId, isLocked }) => {
      await queryClient.cancelQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      const previous = queryClient.getQueryData<NoteTreeResponse>(
        projectDataQueryKeys.notes.tree(projectId),
      );
      if (previous) {
        queryClient.setQueryData<NoteTreeResponse>(
          projectDataQueryKeys.notes.tree(projectId),
          (tree) => {
            if (!tree) return tree;
            return applyToNote(tree, noteId, (note) => ({ ...note, isLocked }));
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(projectDataQueryKeys.notes.tree(projectId), context.previous);
      }
      toast.error(t("writing.noteLockToggleFailed"));
    },
    onSuccess: (updatedNote) => {
      queryClient.setQueryData(projectDataQueryKeys.notes.detail(updatedNote.id), updatedNote);
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.notes.tree(updatedNote.projectId),
      });
      toast.success(
        updatedNote.isLocked ? t("writing.noteLockedToast") : t("writing.noteUnlockedToast"),
      );
    },
  });
}

export function useCreateNoteCategory(projectId: string, documentType: DocumentType = "note") {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (data: NoteCategoryCreate) =>
      createNoteCategory(projectId, { ...data, documentType }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.notes.tree(projectId, documentType),
      });
      toast.success(t("writing.categoryCreated"));
    },
    onError: () => {
      toast.error(t("writing.categoryCreateFailed"));
    },
  });
}

export function useUpdateNoteCategory(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: ({ categoryId, data }: { categoryId: string; data: NoteCategoryUpdate }) =>
      updateNoteCategory(categoryId, data),
    onMutate: async ({ categoryId, data }) => {
      await queryClient.cancelQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      const previous = queryClient.getQueryData<NoteTreeResponse>(
        projectDataQueryKeys.notes.tree(projectId),
      );
      if (previous && data.title !== undefined) {
        queryClient.setQueryData<NoteTreeResponse>(
          projectDataQueryKeys.notes.tree(projectId),
          (tree) => {
            if (!tree) return tree;
            return applyToCategory(tree, categoryId, (cat) => ({ ...cat, title: data.title! }));
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(projectDataQueryKeys.notes.tree(projectId), context.previous);
      }
      toast.error(t("writing.categoryRenameFailed"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      toast.success(t("writing.categoryRenamed"));
    },
  });
}

export function useDeleteNoteCategory(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (categoryId: string) => deleteNoteCategory(categoryId),
    onMutate: async (categoryId) => {
      await queryClient.cancelQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      const previous = queryClient.getQueryData<NoteTreeResponse>(
        projectDataQueryKeys.notes.tree(projectId),
      );
      if (previous) {
        queryClient.setQueryData<NoteTreeResponse>(
          projectDataQueryKeys.notes.tree(projectId),
          (tree) => {
            if (!tree) return tree;
            return removeCategoryFromTree(tree, categoryId);
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(projectDataQueryKeys.notes.tree(projectId), context.previous);
      }
      toast.error(t("writing.deleteCategoryFailed"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      toast.success(t("writing.deleteNoteSuccess"));
    },
  });
}

export function useMoveNoteItem(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (data: NoteItemMove) => moveNoteItem(data),
    onMutate: async ({ kind, itemId, targetCategoryId }) => {
      await queryClient.cancelQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      const previous = queryClient.getQueryData<NoteTreeResponse>(
        projectDataQueryKeys.notes.tree(projectId),
      );
      if (previous) {
        queryClient.setQueryData<NoteTreeResponse>(
          projectDataQueryKeys.notes.tree(projectId),
          (tree) => {
            if (!tree) return tree;
            if (kind === "note") {
              return moveNoteInTree(tree, itemId, targetCategoryId ?? null);
            }
            return moveCategoryInTree(tree, itemId, targetCategoryId ?? null);
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(projectDataQueryKeys.notes.tree(projectId), context.previous);
      }
      toast.error(t("writing.noteMoveFailed"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
    },
  });
}

export function useReorderNoteItems(projectId: string, documentType: DocumentType = "note") {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (data: NoteItemReorder) => reorderNoteItems(projectId, { ...data, documentType }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      toast.success(t("writing.orderSaved"));
    },
    onError: () => {
      toast.error(t("writing.orderSaveFailed"));
    },
  });
}

export function useReorderMixedNoteItems(projectId: string, documentType: DocumentType = "note") {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (data: NoteItemsMixedReorder) =>
      reorderMixedNoteItems(projectId, { ...data, documentType }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      toast.success(t("writing.orderSaved"));
    },
    onError: () => {
      toast.error(t("writing.orderSaveFailed"));
    },
  });
}

export function useDuplicateNote(projectId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: async (noteId: string): Promise<Note> => {
      const original = await fetchNote(noteId);
      return createNote(projectId, {
        categoryId: original.categoryId,
        title: `${original.title}-${t("writing.duplicateSuffix")}`,
        content: original.content,
      });
    },
    onSuccess: (newNote) => {
      queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.tree(projectId) });
      toast.success(t("writing.noteDuplicated"));
      return newNote;
    },
    onError: () => {
      toast.error(t("writing.noteDuplicateFailed"));
    },
  });
}
