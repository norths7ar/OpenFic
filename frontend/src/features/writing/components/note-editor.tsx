import { Flex, Text } from "@radix-ui/themes";
import { useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownEditor, Spinner } from "@/components";
import { toast } from "@/components/toast";
import {
  getEditorContentLimit,
  MAX_EDITOR_CONTENT_CHARACTERS,
  MAX_EDITOR_CONTENT_LINES,
} from "@/lib/editor-content-limits";
import type { Note } from "@/lib/note.types";
import { createToastThrottler } from "@/lib/ui-utils";

import { useAutoSave } from "../hooks/use-auto-save";
import { useUpdateNote } from "../hooks/use-notes";
import {
  invalidateWritingEditorEntityQueries,
  shouldShowWritingEditorLoading,
  useWritingEditorEntity,
} from "../hooks/use-writing-editor-entity";
import {
  useWritingWorkingCopy,
  type WritingDraft,
  type WritingWorkingCopyController,
} from "../hooks/use-writing-working-copy";
import { fetchNote } from "../lib/note-api";
import {
  areWritingWorkingCopyDraftsEqual,
  getNextWritingWorkingCopyTimestamp,
  isRemoteWritingEntityNewer,
} from "../lib/writing-working-copy";
import type { WritingWorkingCopyConflict } from "../lib/writing-working-copy";
import { useTabsStore } from "../store/use-tabs-store";
import { WritingConflictDialog } from "./writing-conflict-dialog";

interface NoteEditorProps {
  noteId: string | null;
  scrollTop?: number;
  projectId?: string;
  isAgentLocked?: boolean;
  onScrollPositionChange?: (noteId: string, scrollTop: number) => void;
  onAddToConversation?: (markup: string) => void;
}

interface NoteEditorContentProps {
  note: Note;
  scrollTop: number;
  initialDraft: WritingDraft;
  initialDraftUpdatedAt: Date;
  baseUpdatedAt: string;
  baseDraft?: WritingDraft;
  conflict?: WritingWorkingCopyConflict;
  workingCopy: WritingWorkingCopyController;
  isAgentLocked?: boolean;
  onScrollPositionChange?: (noteId: string, scrollTop: number) => void;
}

function NoteEditorContent({
  note,
  scrollTop,
  initialDraft,
  initialDraftUpdatedAt,
  baseUpdatedAt,
  baseDraft,
  conflict,
  workingCopy,
  isAgentLocked = false,
  onScrollPositionChange,
}: NoteEditorContentProps) {
  const { t } = useTranslation();
  const updateMutation = useUpdateNote(note.projectId, note.documentType);
  const queryClient = useQueryClient();
  const { updateTabTitle } = useTabsStore();
  const { clearWorkingCopy, discardWorkingCopy, persistWorkingCopy } = workingCopy;

  const showLockedToast = useMemo(
    () => createToastThrottler(t("writing.agentLockedNoteEdit")),
    [t],
  );

  const [title, setTitle] = useState(initialDraft.title);
  const titleRef = useRef(initialDraft.title);
  const [hasChanges, setHasChanges] = useState(
    !areWritingWorkingCopyDraftsEqual(initialDraft, { title: note.title, content: note.content }),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [editorContent, setEditorContent] = useState(initialDraft.content);
  const savedContentRef = useRef(initialDraft.content);
  const latestDraftRef = useRef(initialDraft);
  const latestDraftUpdatedAtRef = useRef(initialDraftUpdatedAt);
  const hasChangesRef = useRef(
    !areWritingWorkingCopyDraftsEqual(initialDraft, { title: note.title, content: note.content }),
  );
  const lastSavedDraftRef = useRef<WritingDraft>({
    title: note.title,
    content: note.content,
  });
  const baseDraftRef = useRef({
    title: baseDraft?.title,
    content: baseDraft?.content,
    updatedAt: baseUpdatedAt,
  });
  const rejectedContentRef = useRef<string | null>(null);

  const showContentLimitToast = useCallback(
    (content: string) => {
      if (rejectedContentRef.current === content) return;
      rejectedContentRef.current = content;
      const { lineCount, characterCount } = getEditorContentLimit(content);
      toast.error(
        t("common.editorContentTooLarge", {
          lineCount,
          characterCount,
          maxLines: MAX_EDITOR_CONTENT_LINES,
          maxCharacters: MAX_EDITOR_CONTENT_CHARACTERS,
        }),
      );
    },
    [t],
  );

  const persistDraft = useCallback(
    (draft: WritingDraft) => {
      latestDraftUpdatedAtRef.current = getNextWritingWorkingCopyTimestamp(
        latestDraftUpdatedAtRef.current,
      );
      persistWorkingCopy(draft, baseDraftRef.current, latestDraftUpdatedAtRef.current);
    },
    [persistWorkingCopy],
  );

  const handleSave = useCallback(async () => {
    if (isAgentLocked) {
      showLockedToast();
      return;
    }

    const draftToSave = latestDraftRef.current;
    const draftUpdatedAt = latestDraftUpdatedAtRef.current;
    const contentLimit = getEditorContentLimit(draftToSave.content);
    if (!contentLimit.isWithinLimit) {
      persistWorkingCopy(draftToSave, baseDraftRef.current, draftUpdatedAt);
      hasChangesRef.current = true;
      setHasChanges(true);
      showContentLimitToast(draftToSave.content);
      return;
    }
    rejectedContentRef.current = null;

    setIsSaving(true);
    try {
      persistWorkingCopy(draftToSave, baseDraftRef.current, draftUpdatedAt);
      const updatedNote = await updateMutation.mutateAsync({
        noteId: note.id,
        data: {
          title: draftToSave.title,
          content: draftToSave.content,
          baseUpdatedAt: baseDraftRef.current.updatedAt,
          ...(baseDraftRef.current.title !== undefined && baseDraftRef.current.content !== undefined
            ? {
                baseTitle: baseDraftRef.current.title,
                baseContent: baseDraftRef.current.content,
              }
            : {}),
        },
      });
      lastSavedDraftRef.current = {
        title: updatedNote.title,
        content: updatedNote.content,
      };
      baseDraftRef.current = {
        title: updatedNote.title,
        content: updatedNote.content,
        updatedAt: updatedNote.updatedAt,
      };
      void clearWorkingCopy(draftToSave, draftUpdatedAt);
      updateTabTitle(`note:${updatedNote.id}`, latestDraftRef.current.title);
      const isDirty = !areWritingWorkingCopyDraftsEqual(
        latestDraftRef.current,
        lastSavedDraftRef.current,
      );
      hasChangesRef.current = isDirty;
      setHasChanges(isDirty);
    } catch {
      await persistWorkingCopy(draftToSave, baseDraftRef.current, draftUpdatedAt);
      invalidateWritingEditorEntityQueries(queryClient, "note", note.id);
      hasChangesRef.current = true;
      setHasChanges(true);
    } finally {
      setIsSaving(false);
    }
  }, [
    clearWorkingCopy,
    isAgentLocked,
    note.id,
    persistWorkingCopy,
    showLockedToast,
    showContentLimitToast,
    updateMutation,
    updateTabTitle,
    queryClient,
  ]);

  useEffect(() => {
    titleRef.current = title;
  }, [title]);

  useEffect(() => {
    if (hasChanges || !isRemoteWritingEntityNewer(note.updatedAt, baseDraftRef.current.updatedAt)) {
      return;
    }

    const draft = { title: note.title, content: note.content ?? "" };
    latestDraftRef.current = draft;
    savedContentRef.current = draft.content;
    setEditorContent(draft.content);
    lastSavedDraftRef.current = draft;
    baseDraftRef.current = { title: note.title, content: note.content, updatedAt: note.updatedAt };
    latestDraftUpdatedAtRef.current = new Date(note.updatedAt);

    if (title !== draft.title) {
      titleRef.current = note.title;
      queueMicrotask(() => {
        setTitle(draft.title);
        updateTabTitle(`note:${note.id}`, note.title);
      });
    }
  }, [note.title, note.content, note.id, note.updatedAt, hasChanges, title, updateTabTitle]);

  useEffect(() => {
    return () => {
      if (hasChangesRef.current) {
        persistWorkingCopy(
          latestDraftRef.current,
          baseDraftRef.current,
          latestDraftUpdatedAtRef.current,
        );
      }
    };
  }, [persistWorkingCopy]);

  useAutoSave({
    onSave: handleSave,
    hasChanges,
    enabled: !isAgentLocked,
    interval: 3000,
  });

  const handleTitleChange = (newTitle: string) => {
    setTitle(newTitle);
    titleRef.current = newTitle;
    const draft = { title: newTitle, content: savedContentRef.current };
    latestDraftRef.current = draft;
    const isDirty = !areWritingWorkingCopyDraftsEqual(draft, lastSavedDraftRef.current);
    hasChangesRef.current = isDirty;
    setHasChanges(isDirty);
    if (isDirty) {
      persistDraft(draft);
    }
    updateTabTitle(`note:${note.id}`, newTitle);
  };

  const handleContentChange = useCallback(
    (markdown: string) => {
      savedContentRef.current = markdown;
      setEditorContent(markdown);
      const draft = { title, content: markdown };
      latestDraftRef.current = draft;
      const isDirty = !areWritingWorkingCopyDraftsEqual(draft, lastSavedDraftRef.current);
      hasChangesRef.current = isDirty;
      setHasChanges(isDirty);
      if (isDirty) {
        persistDraft(draft);
      }
    },
    [persistDraft, title],
  );

  const handleScrollPositionChange = useCallback(
    (nextScrollTop: number) => {
      onScrollPositionChange?.(note.id, nextScrollTop);
    },
    [note.id, onScrollPositionChange],
  );

  const lockedBanner = note.isLocked ? (
    <Flex
      px="4"
      py="2"
      align="center"
      gap="2"
      style={{
        background: "var(--yellow-a3)",
        borderBottom: "1px solid var(--yellow-a5)",
      }}
    >
      <Lock
        size={14}
        style={{ color: "var(--yellow-10)" }}
      />
      <Text
        size="1"
        style={{ color: "var(--yellow-10)" }}
      >
        {t(note.documentType === "outline" ? "writing.outlineLocked" : "writing.noteLocked")}
      </Text>
    </Flex>
  ) : undefined;

  return (
    <>
      {conflict ? (
        <WritingConflictDialog
          conflict={conflict}
          onAdoptLocal={async () => {
            const saved = { title: note.title, content: note.content };
            lastSavedDraftRef.current = saved;
            baseDraftRef.current = {
              title: note.title,
              content: note.content,
              updatedAt: note.updatedAt,
            };
            const isDirty = !areWritingWorkingCopyDraftsEqual(latestDraftRef.current, saved);
            hasChangesRef.current = isDirty;
            setHasChanges(isDirty);
            if (isDirty) {
              await persistWorkingCopy(
                latestDraftRef.current,
                baseDraftRef.current,
                latestDraftUpdatedAtRef.current,
              );
            }
          }}
          onUseSaved={async () => {
            await discardWorkingCopy();
            const saved = { title: note.title, content: note.content };
            latestDraftRef.current = saved;
            lastSavedDraftRef.current = saved;
            baseDraftRef.current = { ...saved, updatedAt: note.updatedAt };
            savedContentRef.current = saved.content;
            setTitle(saved.title);
            setEditorContent(saved.content);
            updateTabTitle(`note:${note.id}`, saved.title);
            setHasChanges(false);
            hasChangesRef.current = false;
          }}
        />
      ) : null}
      <MarkdownEditor
        title={title}
        onTitleChange={handleTitleChange}
        content={editorContent}
        onContentChange={handleContentChange}
        onSave={handleSave}
        isSaving={isSaving}
        hasChanges={hasChanges}
        isLocked={isAgentLocked}
        onLockedAction={showLockedToast}
        placeholder={t(
          note.documentType === "outline"
            ? "writing.outlineContentPlaceholder"
            : "writing.noteContentPlaceholder",
        )}
        lockedBanner={lockedBanner}
        scrollTop={scrollTop}
        onScrollPositionChange={handleScrollPositionChange}
      />
    </>
  );
}

export function NoteEditor(props: NoteEditorProps) {
  const { t } = useTranslation();
  const { data } = useWritingEditorEntity({
    type: "note",
    entityId: props.noteId,
    fetchEntity: fetchNote,
  });

  if (!props.noteId) {
    return (
      <Flex
        align="center"
        justify="center"
        style={{ flex: 1, minHeight: 0 }}
      >
        <Text
          color="gray"
          size="3"
        >
          {t("writing.selectNote")}
        </Text>
      </Flex>
    );
  }

  if (shouldShowWritingEditorLoading(data)) {
    return (
      <Flex
        align="center"
        justify="center"
        style={{ flex: 1, minHeight: 0, height: "100%" }}
      >
        <Spinner size={18} />
      </Flex>
    );
  }

  return (
    <NoteEditorWorkingCopy
      key={`${data.entity.id}:${data.draftUpdatedAt.getTime()}`}
      note={data.entity}
      scrollTop={props.scrollTop ?? 0}
      initialDraft={data.draft}
      initialDraftUpdatedAt={data.draftUpdatedAt}
      baseUpdatedAt={data.baseUpdatedAt}
      baseDraft={data.baseDraft}
      conflict={data.conflict}
      isAgentLocked={props.isAgentLocked ?? false}
      onScrollPositionChange={props.onScrollPositionChange}
    />
  );
}

function NoteEditorWorkingCopy({
  note,
  scrollTop,
  initialDraft,
  initialDraftUpdatedAt,
  baseUpdatedAt,
  baseDraft,
  conflict,
  isAgentLocked,
  onScrollPositionChange,
}: Omit<NoteEditorContentProps, "workingCopy">) {
  const workingCopy = useWritingWorkingCopy({
    type: "note",
    entityId: note.id,
  });

  return (
    <NoteEditorContent
      key={`${note.id}:${initialDraftUpdatedAt.getTime()}`}
      note={note}
      scrollTop={scrollTop}
      initialDraft={initialDraft}
      initialDraftUpdatedAt={initialDraftUpdatedAt}
      baseUpdatedAt={baseUpdatedAt}
      baseDraft={baseDraft}
      conflict={conflict}
      workingCopy={workingCopy}
      isAgentLocked={isAgentLocked}
      onScrollPositionChange={onScrollPositionChange}
    />
  );
}
