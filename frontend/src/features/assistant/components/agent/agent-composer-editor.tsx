import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Placeholder from "@tiptap/extension-placeholder";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import type { Editor } from "@tiptap/react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ClipboardEvent as ReactClipboardEvent,
  DragEvent as ReactDragEvent,
  KeyboardEvent as ReactKeyboardEvent,
} from "react";

import {
  buildSkillCommandTag,
  findActiveCommandQuery,
} from "@/features/assistant/lib/command-text";
import type { AssistantMentionCandidate } from "@/features/assistant/lib/mention-text";
import {
  buildCharacterMentionTag,
  buildChapterMentionTag,
  buildNoteCategoryMentionTag,
  buildNoteMentionTag,
  buildVolumeMentionTag,
  buildWorldInfoEntryMentionTag,
  findActiveMentionQuery,
  mentionTextToHtml,
  parseAssistantMarkup,
} from "@/features/assistant/lib/mention-text";
import type { AssistantCommandCandidate } from "@/lib/command.types";

import { searchCommands, searchMentionCandidates } from "../../lib/agent-composer-api";
import type { AgentInputHistoryDirection } from "../../lib/agent-input-history-state";
import { CommandNode } from "./extensions/command-node";
import type { AssistantCommandNodeAttributes } from "./extensions/command-node";
import { MentionNode } from "./extensions/mention-node";
import type { AssistantMentionNodeAttributes } from "./extensions/mention-node";

export type AgentComposerSuggestionStatus = "idle" | "loading" | "empty" | "ready";
export type AgentComposerSuggestionMode = "mention" | "command";
export type AgentComposerSuggestionItem = AssistantMentionCandidate | AssistantCommandCandidate;

export interface AgentMentionBrowser {
  kind: AssistantMentionCandidate["kind"] | "all";
  folderId: string;
  folders: { id: string; title: string }[];
  hasMore: boolean;
  isLoadingMore: boolean;
  onKindChange: (kind: AssistantMentionCandidate["kind"] | "all") => void;
  onFolderChange: (folderId: string) => void;
  onLoadMore: () => void;
}

const EMPTY_SUGGESTION_ITEMS: AgentComposerSuggestionItem[] = [];

export interface AgentComposerSuggestionState {
  browser?: AgentMentionBrowser;
  mode: AgentComposerSuggestionMode;
  items: AgentComposerSuggestionItem[];
  selectedIndex: number;
  status: AgentComposerSuggestionStatus;
  onClose: () => void;
  onSelect: (item: AgentComposerSuggestionItem, index: number) => void;
  onSelectedIndexChange: (index: number) => void;
}

interface AgentComposerEditorProps {
  projectId: string;
  contextMode?: "global" | "local";
  value: string;
  placeholder: string;
  disabled: boolean;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
  onMentionSuggestionsChange?: (state: AgentComposerSuggestionState | null) => void;
  onPasteFiles?: (dataTransfer: DataTransfer) => void;
  onDropFiles?: (dataTransfer: DataTransfer) => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onHistoryNavigate?: (direction: AgentInputHistoryDirection) => boolean;
  historyNavigationActive?: boolean;
}

interface MentionQueryState {
  mode: AgentComposerSuggestionMode;
  query: string;
  replaceFrom: number;
  visible: boolean;
}

function createClosedMentionQueryState(): MentionQueryState {
  return {
    mode: "mention",
    query: "",
    replaceFrom: -1,
    visible: false,
  };
}

function hasFiles(dataTransfer: DataTransfer): boolean {
  return (
    dataTransfer.files.length > 0 ||
    Array.from(dataTransfer.items).some((item) => item.kind === "file")
  );
}

function docToCanonicalText(doc: ProseMirrorNode): string {
  const paragraphs: string[] = [];

  doc.forEach((node) => {
    let current = "";
    node.forEach((child) => {
      if (child.isText) {
        current += child.text ?? "";
        return;
      }
      if (child.type.name === "assistantMention") {
        current += String(child.attrs.mentionRaw ?? "");
        return;
      }
      if (child.type.name === "assistantCommand") {
        current += String(child.attrs.commandRaw ?? "");
      }
    });
    paragraphs.push(current);
  });

  return paragraphs.join("\n");
}

function createMentionNodeAttrs(
  candidate: AssistantMentionCandidate,
): AssistantMentionNodeAttributes {
  const mentionRaw =
    candidate.kind === "volume"
      ? buildVolumeMentionTag({
          volumeId: candidate.id,
          label: candidate.label,
        })
      : candidate.kind === "character"
        ? buildCharacterMentionTag({
            characterId: candidate.id,
            label: candidate.label,
          })
        : candidate.kind === "note"
          ? buildNoteMentionTag({
              noteId: candidate.id,
              label: candidate.label,
            })
          : candidate.kind === "world_info_entry"
            ? buildWorldInfoEntryMentionTag({
                worldInfoEntryId: candidate.id,
                label: candidate.label,
              })
            : candidate.kind === "note_category"
              ? buildNoteCategoryMentionTag({
                  categoryId: candidate.id,
                  label: candidate.label,
                })
              : buildChapterMentionTag({
                  chapterId: candidate.id,
                  label: candidate.label,
                });

  return {
    mentionKind: candidate.kind,
    mentionLabel: candidate.label,
    mentionRaw,
    mentionBody: "",
    volumeId: candidate.kind === "volume" ? candidate.id : "",
    chapterId: candidate.kind === "chapter" ? candidate.id : "",
    noteId: candidate.kind === "note" ? candidate.id : "",
    noteCategoryId: candidate.kind === "note_category" ? candidate.id : "",
    worldInfoEntryId: candidate.kind === "world_info_entry" ? candidate.id : "",
    characterId: candidate.kind === "character" ? candidate.id : "",
    lineStart: "",
    lineEnd: "",
  };
}

function createCommandNodeAttrs(
  candidate: AssistantCommandCandidate,
): AssistantCommandNodeAttributes {
  const commandRaw = buildSkillCommandTag(candidate.id, candidate.name);
  return {
    commandKind: candidate.kind,
    commandLabel: candidate.name,
    commandRaw,
    commandId: candidate.id,
    commandName: candidate.name,
  };
}

export function AgentComposerEditor({
  projectId,
  contextMode = "local",
  value,
  placeholder,
  disabled,
  onOpenMentionChapter,
  onMentionSuggestionsChange,
  onPasteFiles,
  onDropFiles,
  onChange,
  onSubmit,
  onHistoryNavigate,
  historyNavigationActive = false,
}: AgentComposerEditorProps) {
  const isApplyingExternalValueRef = useRef(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mentionKind, setMentionKind] = useState<AgentMentionBrowser["kind"]>("all");
  const [folderId, setFolderId] = useState("all");
  const [mentionQuery, setMentionQuery] = useState<MentionQueryState>(
    createClosedMentionQueryState,
  );

  const normalizedQuery = mentionQuery.query.trim();
  const shouldSearchSuggestionItems = mentionQuery.visible && projectId.trim().length > 0;
  const commandQuery = useQuery({
    queryKey: ["assistant-composer-commands", projectId, normalizedQuery],
    queryFn: ({ signal }) => searchCommands(projectId, normalizedQuery, 20, "skill", signal),
    enabled: shouldSearchSuggestionItems && mentionQuery.mode === "command",
    staleTime: 30 * 1000,
  });
  const candidatesQuery = useInfiniteQuery({
    queryKey: [
      "assistant-composer-candidates",
      projectId,
      contextMode,
      normalizedQuery,
      mentionKind,
      folderId,
    ],
    initialPageParam: 0,
    queryFn: ({ signal, pageParam }) =>
      searchMentionCandidates(
        projectId,
        normalizedQuery,
        20,
        mentionKind === "all" ? undefined : mentionKind,
        signal,
        { contextMode, folderId: folderId === "all" ? undefined : folderId, offset: pageParam },
      ),
    getNextPageParam: (page, pages) =>
      page.hasMore ? pages.reduce((count, item) => count + item.items.length, 0) : undefined,
    enabled: shouldSearchSuggestionItems && mentionQuery.mode === "mention",
    staleTime: 30 * 1000,
  });
  const mentionItems = useMemo(
    () => candidatesQuery.data?.pages.flatMap((page) => page.items),
    [candidatesQuery.data],
  );
  const isSearchingSuggestionItems =
    mentionQuery.mode === "command"
      ? commandQuery.isFetching
      : candidatesQuery.isFetching && !candidatesQuery.isFetchingNextPage;
  const suggestionItems = shouldSearchSuggestionItems
    ? ((mentionQuery.mode === "command" ? commandQuery.data : mentionItems) ??
      EMPTY_SUGGESTION_ITEMS)
    : EMPTY_SUGGESTION_ITEMS;
  const suggestionStatus: AgentComposerSuggestionStatus | null = !mentionQuery.visible
    ? null
    : isSearchingSuggestionItems
      ? "loading"
      : suggestionItems.length > 0
        ? "ready"
        : "empty";
  const { fetchNextPage } = candidatesQuery;
  const browser = useMemo<AgentMentionBrowser>(
    () => ({
      kind: mentionKind,
      folderId,
      folders: candidatesQuery.data?.pages[0]?.folders ?? [],
      hasMore: candidatesQuery.hasNextPage,
      isLoadingMore: candidatesQuery.isFetchingNextPage,
      onKindChange: (kind) => {
        setMentionKind(kind);
        setFolderId("all");
        setSelectedIndex(0);
      },
      onFolderChange: (id) => {
        setFolderId(id);
        setSelectedIndex(0);
      },
      onLoadMore: () => {
        void fetchNextPage();
      },
    }),
    [
      mentionKind,
      folderId,
      candidatesQuery.data,
      candidatesQuery.hasNextPage,
      candidatesQuery.isFetchingNextPage,
      fetchNextPage,
    ],
  );
  const effectiveSelectedIndex =
    suggestionStatus === "ready" && suggestionItems.length > 0
      ? Math.min(selectedIndex, suggestionItems.length - 1)
      : 0;

  const extensions = useMemo(
    () => [
      StarterKit.configure({
        heading: false,
        bold: false,
        italic: false,
        strike: false,
        code: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        hardBreak: false,
      }),
      Placeholder.configure({
        placeholder,
      }),
      MentionNode.configure({
        onOpenMentionChapter,
      }),
      CommandNode,
    ],
    [onOpenMentionChapter, placeholder],
  );

  const editor = useEditor({
    extensions,
    content: mentionTextToHtml(value),
    editable: !disabled,
    editorProps: {
      attributes: {
        class: "agent-composer-prosemirror",
      },
    },
    onCreate: ({ editor: instance }) => {
      const next = docToCanonicalText(instance.state.doc);
      if (next !== value) {
        isApplyingExternalValueRef.current = true;
        instance.commands.setContent(mentionTextToHtml(value), { emitUpdate: false });
        isApplyingExternalValueRef.current = false;
      }
    },
    onUpdate: ({ editor: instance }) => {
      if (isApplyingExternalValueRef.current) return;
      onChange(docToCanonicalText(instance.state.doc));
      updateMentionQuery(instance);
    },
    onSelectionUpdate: ({ editor: instance }) => {
      updateMentionQuery(instance);
    },
  });

  useEffect(() => {
    if (!editor) return;
    if (docToCanonicalText(editor.state.doc) === value) return;

    isApplyingExternalValueRef.current = true;
    editor.commands.setContent(mentionTextToHtml(value), { emitUpdate: false });
    isApplyingExternalValueRef.current = false;
  }, [editor, value]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      if (suggestionStatus !== "ready" || suggestionItems.length === 0) {
        setSelectedIndex(0);
        return;
      }
      setSelectedIndex((current) => Math.min(current, suggestionItems.length - 1));
    });
    return () => {
      cancelled = true;
    };
  }, [suggestionItems.length, suggestionStatus]);

  const updateMentionQuery = useCallback(
    (instance: Editor) => {
      if (disabled) {
        setMentionQuery((current) => (current.visible ? createClosedMentionQueryState() : current));
        return;
      }

      const selection = instance.state.selection;
      if (!selection.empty) {
        setMentionQuery((current) => (current.visible ? createClosedMentionQueryState() : current));
        return;
      }

      const { from, $from } = selection;
      const textBefore = $from.parent.textBetween(0, $from.parentOffset, undefined, "\ufffc");
      const activeCommandQuery = findActiveCommandQuery(textBefore);
      const activeMentionQuery = findActiveMentionQuery(textBefore);
      const activeQuery = activeCommandQuery ?? activeMentionQuery;
      if (!activeQuery) {
        setMentionQuery((current) => (current.visible ? createClosedMentionQueryState() : current));
        return;
      }

      setMentionQuery({
        mode: activeCommandQuery ? "command" : "mention",
        query: activeQuery.query,
        replaceFrom: from - activeQuery.replaceLength,
        visible: true,
      });
    },
    [disabled],
  );

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(!disabled);
  }, [disabled, editor]);

  useEffect(() => {
    if (!editor) return;
    const nextCanonicalText = docToCanonicalText(editor.state.doc);
    if (nextCanonicalText === value) return;
    isApplyingExternalValueRef.current = true;
    editor.commands.setContent(mentionTextToHtml(value), { emitUpdate: false });
    isApplyingExternalValueRef.current = false;
    updateMentionQuery(editor);
  }, [editor, updateMentionQuery, value]);

  useEffect(() => {
    if (!editor) return;
    const parsedSegments = parseAssistantMarkup(value);
    const hasOnlyMentions =
      parsedSegments.length > 0 &&
      parsedSegments.every((segment) => typeof segment !== "string" || !segment.trim());
    if (hasOnlyMentions && !value.includes("\n") && !editor.isFocused) {
      editor.commands.focus("end");
    }
  }, [editor, value]);

  const closeSuggestions = useCallback(() => {
    setMentionQuery(createClosedMentionQueryState());
    setSelectedIndex(0);
  }, []);

  const handleSelectSuggestion = useCallback(
    (candidate: AgentComposerSuggestionItem, index: number) => {
      if (!editor || mentionQuery.replaceFrom < 0) return;
      const currentSelectionTo = editor.state.selection.from;
      setSelectedIndex(index);
      const chain = editor
        .chain()
        .focus()
        .deleteRange({ from: mentionQuery.replaceFrom, to: currentSelectionTo });
      if (candidate.kind === "skill") {
        chain.insertAssistantCommand(createCommandNodeAttrs(candidate));
      } else {
        chain.insertAssistantMention(createMentionNodeAttrs(candidate));
      }
      chain.insertContent(" ").run();
      closeSuggestions();
    },
    [closeSuggestions, editor, mentionQuery.replaceFrom],
  );

  const handleEditorKeyDownCapture = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.nativeEvent.isComposing || event.keyCode === 229) return;
      if (
        !disabled &&
        !mentionQuery.visible &&
        editor &&
        !event.shiftKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !event.metaKey &&
        (event.key === "ArrowUp" || event.key === "ArrowDown")
      ) {
        const { selection } = editor.state;
        const isAtBoundary =
          selection.empty &&
          (event.key === "ArrowUp"
            ? selection.from <= 1
            : selection.to >= editor.state.doc.content.size - 1);
        if (historyNavigationActive || isAtBoundary) {
          const direction = event.key === "ArrowUp" ? "older" : "newer";
          if (onHistoryNavigate?.(direction)) {
            event.preventDefault();
            return;
          }
        }
      }

      if (event.key !== "Enter") return;
      // 输入法确认候选词不应发送消息，也不应插入额外换行。
      if (event.nativeEvent.isComposing || event.keyCode === 229) return;
      if (event.shiftKey) {
        if (!editor) return;
        event.preventDefault();
        editor.commands.splitBlock();
        return;
      }
      if (suggestionStatus === "ready" && suggestionItems.length > 0) return;
      event.preventDefault();
      onSubmit();
    },
    [
      disabled,
      editor,
      mentionQuery.visible,
      onHistoryNavigate,
      historyNavigationActive,
      onSubmit,
      suggestionItems.length,
      suggestionStatus,
    ],
  );

  const handlePasteCapture = (event: ReactClipboardEvent<HTMLDivElement>) => {
    if (!onPasteFiles || !hasFiles(event.clipboardData)) return;
    event.preventDefault();
    event.stopPropagation();
    onPasteFiles(event.clipboardData);
  };

  const handleDragOverCapture = (event: ReactDragEvent<HTMLDivElement>) => {
    if (!hasFiles(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDropCapture = (event: ReactDragEvent<HTMLDivElement>) => {
    if (!onDropFiles || !hasFiles(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    onDropFiles(event.dataTransfer);
  };

  useEffect(() => {
    if (!editor) return;
    updateMentionQuery(editor);
  }, [editor, updateMentionQuery]);

  useEffect(() => {
    if (!onMentionSuggestionsChange) return;

    if (!mentionQuery.visible || !suggestionStatus) {
      onMentionSuggestionsChange(null);
      return;
    }

    onMentionSuggestionsChange({
      browser: mentionQuery.mode === "mention" ? browser : undefined,
      mode: mentionQuery.mode,
      items: suggestionItems,
      selectedIndex: effectiveSelectedIndex,
      status: suggestionStatus,
      onClose: closeSuggestions,
      onSelect: handleSelectSuggestion,
      onSelectedIndexChange: setSelectedIndex,
    });
  }, [
    browser,
    closeSuggestions,
    effectiveSelectedIndex,
    handleSelectSuggestion,
    mentionQuery.mode,
    mentionQuery.visible,
    onMentionSuggestionsChange,
    suggestionItems,
    suggestionStatus,
  ]);

  useEffect(
    () => () => {
      onMentionSuggestionsChange?.(null);
    },
    [onMentionSuggestionsChange],
  );

  return (
    <div
      className="agent-composer-editor"
      data-disabled={disabled}
      onKeyDownCapture={handleEditorKeyDownCapture}
      onPasteCapture={handlePasteCapture}
      onDragOverCapture={handleDragOverCapture}
      onDropCapture={handleDropCapture}
    >
      <EditorContent editor={editor} />
    </div>
  );
}
