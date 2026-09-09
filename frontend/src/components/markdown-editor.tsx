import type { Transaction } from "@tiptap/pm/state";
import { useEditor, EditorContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import { useCallback, useRef, useEffect, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { useTranslation } from "react-i18next";

import type { DocumentHistoryConfig } from "@/features/workspace/components/document-history";

import { ContextMenu } from "./context-menu";
import { EditorDraftHistory } from "./editor-draft-history";
import { EditorFrame } from "./editor-frame";
import type { EditorToolbarExtraAction } from "./editor-toolbar";
import { createMarkdownEditorExtensions } from "./markdown-editor-config";

export interface MarkdownEditorProps {
  documentHistory?: DocumentHistoryConfig;
  title: string;
  onTitleChange: (title: string) => void;
  content: string;
  onContentChange: (markdown: string) => void;
  onSave: () => void;
  isSaving?: boolean;
  hasChanges?: boolean;
  isLocked?: boolean;
  onLockedAction?: () => void;
  placeholder?: string;
  titlePlaceholder?: string;
  extraToolbarActions?: EditorToolbarExtraAction[];
  toolbarPrefix?: React.ReactNode;
  wordCount?: number;
  saveStatusText?: { saving: string; saved: string; unsaved: string };
  wordCountLabel?: string;
  lockedBanner?: React.ReactNode;
  maxWidth?: number;
  editorRef?: React.MutableRefObject<Editor | null>;
  scrollTop?: number;
  onScrollPositionChange?: (scrollTop: number) => void;
}

export function MarkdownEditor({
  title,
  documentHistory,
  onTitleChange,
  content,
  onContentChange,
  onSave,
  isSaving = false,
  hasChanges = false,
  isLocked = false,
  onLockedAction,
  placeholder,
  titlePlaceholder,
  extraToolbarActions,
  toolbarPrefix,
  wordCount: externalWordCount,
  saveStatusText,
  wordCountLabel,
  lockedBanner,
  maxWidth = 800,
  editorRef: externalEditorRef,
  scrollTop = 0,
  onScrollPositionChange,
}: MarkdownEditorProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"visual" | "source">("visual");
  const [rawContent, setRawContent] = useState(content);
  const historyRef = useRef(new EditorDraftHistory(content));
  const contentSyncedRef = useRef(content);
  const editorContentRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const initialScrollTopRef = useRef(scrollTop);
  const latestScrollTopRef = useRef(scrollTop);
  const scrollPositionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollCallbackRef = useRef(onScrollPositionChange);
  useEffect(() => {
    scrollCallbackRef.current = onScrollPositionChange;
  }, [onScrollPositionChange]);

  const editor = useEditor({
    extensions: createMarkdownEditorExtensions({
      placeholder: placeholder ?? "",
      shortcuts: {
        onSave: () => {
          if (isLocked) {
            onLockedAction?.();
            return;
          }
          onSave();
        },
      },
    }),
    content,
    contentType: "markdown",
    editable: !isLocked,
  });
  const editorRef = useRef(editor);

  useEffect(() => {
    editorRef.current = editor;
    if (externalEditorRef) {
      externalEditorRef.current = editor;
    }
  }, [editor, externalEditorRef]);

  useEffect(() => {
    if (!editor) return;
    const onUpdate = ({ transaction }: { transaction: Transaction }) => {
      // setEditable and trailing-node normalization can emit updates without a user edit.
      // Keep the original Markdown until the originating transaction changes content.
      if (!transaction.docChanged) return;
      const markdown = editorRef.current?.getMarkdown();
      if (markdown !== undefined && markdown !== contentSyncedRef.current) {
        contentSyncedRef.current = markdown;
        historyRef.current.record(markdown);
        setRawContent(markdown);
        onContentChange(markdown);
      }
    };
    editor.on("update", onUpdate);
    return () => {
      editor.off("update", onUpdate);
    };
  }, [editor, onContentChange]);

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(!isLocked);
  }, [editor, isLocked]);

  useEffect(() => {
    const currentEditor = editorRef.current;
    if (!currentEditor) return;
    if (content === contentSyncedRef.current) return;

    const { from, to } = currentEditor.state.selection;
    const wasFocused = currentEditor.isFocused;
    contentSyncedRef.current = content;
    historyRef.current = new EditorDraftHistory(content);
    setRawContent(content);
    currentEditor.commands.setContent(content, { contentType: "markdown", emitUpdate: false });
    if (!wasFocused) return;

    const maxPosition = Math.max(1, currentEditor.state.doc.content.size);
    currentEditor.commands.setTextSelection({
      from: Math.min(from, maxPosition),
      to: Math.min(to, maxPosition),
    });
  }, [content]);

  const changeSource = (value: string) => {
    if (isLocked) return;
    contentSyncedRef.current = value;
    historyRef.current.record(value);
    setRawContent(value);
    onContentChange(value);
  };

  const restoreHistory = (direction: "undo" | "redo") => {
    if (isLocked) {
      onLockedAction?.();
      return;
    }
    const value = historyRef.current[direction]();
    contentSyncedRef.current = value;
    setRawContent(value);
    editor?.commands.setContent(value, { contentType: "markdown", emitUpdate: false });
    onContentChange(value);
  };

  const changeMode = (nextMode: "visual" | "source") => {
    historyRef.current.breakGroup();
    if (nextMode === "visual" && mode === "source") {
      editor?.commands.setContent(contentSyncedRef.current, {
        contentType: "markdown",
        emitUpdate: false,
      });
    }
    setMode(nextMode);
  };

  const flushScrollPosition = useCallback(() => {
    if (scrollPositionTimerRef.current) {
      clearTimeout(scrollPositionTimerRef.current);
      scrollPositionTimerRef.current = null;
    }
    const scrollPosition = scrollContainerRef.current?.scrollTop ?? latestScrollTopRef.current;
    latestScrollTopRef.current = scrollPosition;
    scrollCallbackRef.current?.(scrollPosition);
  }, []);

  const handleEditorScroll = useCallback(() => {
    if (!scrollCallbackRef.current) return;

    const scrollPosition = scrollContainerRef.current?.scrollTop;
    if (scrollPosition === undefined) return;

    latestScrollTopRef.current = scrollPosition;
    if (scrollPositionTimerRef.current) return;

    scrollPositionTimerRef.current = setTimeout(() => {
      scrollPositionTimerRef.current = null;
      scrollCallbackRef.current?.(latestScrollTopRef.current);
    }, 250);
  }, []);

  useEffect(() => {
    return flushScrollPosition;
  }, [flushScrollPosition]);

  useEffect(() => {
    if (!editor || !scrollCallbackRef.current) return;

    let restoreFrameId: number | null = null;
    const frameId = window.requestAnimationFrame(() => {
      restoreFrameId = window.requestAnimationFrame(() => {
        const container = scrollContainerRef.current;
        if (!container) return;

        const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
        const restoredScrollTop = Math.min(initialScrollTopRef.current, maxScrollTop);
        container.scrollTop = restoredScrollTop;
        latestScrollTopRef.current = restoredScrollTop;
        if (restoredScrollTop !== initialScrollTopRef.current) {
          scrollCallbackRef.current?.(restoredScrollTop);
        }
      });
    });

    return () => {
      window.cancelAnimationFrame(frameId);
      if (restoreFrameId !== null) window.cancelAnimationFrame(restoreFrameId);
    };
  }, [editor]);

  useHotkeys(
    "mod+s",
    (event) => {
      event.preventDefault();
      if (isLocked) {
        onLockedAction?.();
        return;
      }
      onSave();
    },
    { enableOnFormTags: true },
  );

  const handleTitleBlur = useCallback(() => {
    if (hasChanges && !isLocked) {
      onSave();
    }
  }, [hasChanges, isLocked, onSave]);

  const saveStatus = isSaving ? "saving" : hasChanges ? "unsaved" : "saved";
  const wordCount =
    externalWordCount ??
    (mode === "source" ? rawContent.length : (editor?.storage.characterCount?.characters() ?? 0));

  return (
    <EditorFrame
      banner={lockedBanner}
      toolbar={{
        documentHistory,
        editor,
        onSave,
        isSaving,
        hasChanges,
        isAgentLocked: isLocked,
        onLockedAction,
        extraActions: extraToolbarActions,
        toolbarPrefix,
        mode,
        onModeChange: changeMode,
        history: {
          canUndo: historyRef.current.canUndo,
          canRedo: historyRef.current.canRedo,
          undo: () => restoreHistory("undo"),
          redo: () => restoreHistory("redo"),
        },
      }}
      title={{
        value: title,
        onChange: onTitleChange,
        onBlur: handleTitleBlur,
        disabled: isLocked,
        onDisabledClick: onLockedAction,
        placeholder: titlePlaceholder,
      }}
      scrollRef={scrollContainerRef}
      scrollProps={{ onScroll: handleEditorScroll }}
      maxWidth={maxWidth}
      bodyRef={editorContentRef}
      onBodyKeyDownCapture={(event) => {
        if (event.nativeEvent.isComposing || !(event.ctrlKey || event.metaKey) || event.altKey)
          return;
        const key = event.key.toLowerCase();
        if (key !== "z" && key !== "y") return;
        event.preventDefault();
        event.stopPropagation();
        restoreHistory(key === "y" || event.shiftKey ? "redo" : "undo");
      }}
      statistics={
        <>
          {wordCount} {wordCountLabel ?? t("writing.words")}
        </>
      }
      saveStatus={
        saveStatus === "saving"
          ? (saveStatusText?.saving ?? t("writing.saving"))
          : saveStatus === "saved"
            ? (saveStatusText?.saved ?? t("writing.saved"))
            : (saveStatusText?.unsaved ?? t("writing.unsavedChanges"))
      }
      overlays={
        !isLocked &&
        mode === "visual" && (
          <ContextMenu
            editor={editor}
            containerRef={editorContentRef}
          />
        )
      }
    >
      {mode === "source" ? (
        <textarea
          aria-label={t("editor.sourceMode", "源码")}
          value={rawContent}
          onChange={(event) => changeSource(event.target.value)}
          readOnly={isLocked}
          placeholder={placeholder}
          spellCheck={false}
          style={{
            display: "block",
            width: "100%",
            minHeight: "60vh",
            fieldSizing: "content",
            resize: "none",
            border: 0,
            outline: 0,
            padding: 0,
            background: "transparent",
            color: "inherit",
            fontFamily: "var(--code-font-family)",
            fontSize: "inherit",
            lineHeight: 1.8,
          }}
        />
      ) : (
        <EditorContent
          editor={editor}
          className="tiptap-editor"
        />
      )}
    </EditorFrame>
  );
}
