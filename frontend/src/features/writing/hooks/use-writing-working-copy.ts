import { useCallback } from "react";

import {
  deleteWritingWorkingCopy,
  deleteWritingWorkingCopyIfMatches,
  saveWritingWorkingCopy,
  type WritingWorkingCopyType,
} from "@/lib/local-db";

export interface WritingDraft {
  title: string;
  content: string;
}

export interface WritingWorkingCopyController {
  persistWorkingCopy: (
    draft: WritingDraft,
    base: { updatedAt: string; title?: string; content?: string },
    updatedAt: Date,
  ) => Promise<void>;
  clearWorkingCopy: (draft: WritingDraft, updatedAt: Date) => Promise<void>;
  discardWorkingCopy: () => Promise<void>;
}

interface UseWritingWorkingCopyOptions {
  type: WritingWorkingCopyType;
  entityId: string;
}

export function useWritingWorkingCopy({ type, entityId }: UseWritingWorkingCopyOptions) {
  const persistWorkingCopy = useCallback(
    (
      draft: WritingDraft,
      base: { updatedAt: string; title?: string; content?: string },
      updatedAt: Date,
    ) => {
      const contentBase =
        base.title !== undefined && base.content !== undefined
          ? { baseTitle: base.title, baseContent: base.content }
          : {};
      return saveWritingWorkingCopy({
        entityId,
        type,
        title: draft.title,
        content: draft.content,
        baseUpdatedAt: base.updatedAt,
        ...contentBase,
        updatedAt,
      }).then(() => undefined);
    },
    [entityId, type],
  );

  const clearWorkingCopy = useCallback(
    (draft: WritingDraft, updatedAt: Date) =>
      deleteWritingWorkingCopyIfMatches(type, entityId, draft, updatedAt),
    [entityId, type],
  );

  const discardWorkingCopy = useCallback(
    () => deleteWritingWorkingCopy(type, entityId),
    [entityId, type],
  );

  return {
    persistWorkingCopy,
    clearWorkingCopy,
    discardWorkingCopy,
  };
}
