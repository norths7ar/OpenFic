import { Box, Button, Dialog, DropdownMenu, Flex, IconButton, TextArea } from "@radix-ui/themes";
import {
  FilePlus,
  Plus,
  FolderPlus,
  ExternalLink,
  AtSign,
  Copy,
  Pencil,
  Lock,
  Unlock,
  Trash2,
  Search,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from "lucide-react";
import { motion } from "motion/react";
import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog, ContextMenu, toast } from "@/components";
import type { ContextMenuItem } from "@/components";
import {
  buildNoteCategoryMentionTag,
  buildNoteMentionTag,
} from "@/features/assistant/lib/mention-text";
import { ProjectNavToolbar } from "@/features/project-navigation/components/project-nav-toolbar";
import type { DocumentType, NoteTreeResponse } from "@/lib/note.types";
import { createToastThrottler } from "@/lib/ui-utils";

import {
  useNoteTree,
  useCreateNote,
  useUpdateNote,
  useDeleteNote,
  useCreateNoteCategory,
  useUpdateNoteCategory,
  useDeleteNoteCategory,
  useMoveNoteItem,
  useReorderMixedNoteItems,
  useToggleNoteLock,
  useDuplicateNote,
} from "../hooks/use-notes";
import { NoteFolderList, type NoteSortMode } from "./note-folder-list";
import type { NoteAgentVisibility } from "./note-folder-list";
import { NoteSearchPopover } from "./note-search-popover";

interface NoteSidebarProps {
  selectedNoteId?: string | null;
  projectId: string;
  onNoteSelect: (noteId: string, title: string) => void;
  onAddToConversation?: (markup: string) => void;
  isAgentLocked?: boolean;
  compact?: boolean;
  documentType?: DocumentType;
}

export function NoteSidebar({
  selectedNoteId,
  projectId,
  onNoteSelect,
  onAddToConversation,
  isAgentLocked = false,
  documentType = "note",
}: NoteSidebarProps) {
  const { t } = useTranslation();
  const [descriptionTarget, setDescriptionTarget] = useState<string | null>(null);
  const [folderDescription, setFolderDescription] = useState("");
  const isOutline = documentType === "outline";
  const untitledDocumentLabel = t(isOutline ? "writing.untitledOutline" : "writing.untitledNote");
  const { data } = useNoteTree(projectId, documentType);
  const createNoteMutation = useCreateNote(projectId, documentType);
  const createCategoryMutation = useCreateNoteCategory(projectId, documentType);
  const updateNoteMutation = useUpdateNote(projectId, documentType);
  const updateCategoryMutation = useUpdateNoteCategory(projectId);
  const deleteNoteMutation = useDeleteNote(projectId);
  const deleteCategoryMutation = useDeleteNoteCategory(projectId);
  const moveMutation = useMoveNoteItem(projectId);
  const reorderMutation = useReorderMixedNoteItems(projectId, documentType);
  const toggleLockMutation = useToggleNoteLock(projectId);
  const duplicateNoteMutation = useDuplicateNote(projectId);

  const [contextMenuPos, setContextMenuPos] = useState<{ x: number; y: number } | null>(null);
  const [contextMenuTarget, setContextMenuTarget] = useState<{
    id: string;
    type: "category" | "note";
    title: string;
  } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    type: "category" | "note";
    title: string;
  } | null>(null);
  const [localNoteId, setCurrentNoteId] = useState<string | null>(null);
  const currentNoteId = selectedNoteId === undefined ? localNoteId : selectedNoteId;
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);

  const [contentSearchOpen, setContentSearchOpen] = useState(false);
  const [contentSearchExpanded, setContentSearchExpanded] = useState(false);
  const [contentSearchQuery, setContentSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<NoteSortMode>("manual");
  const searchContainerRef = useRef<HTMLDivElement | null>(null);

  const showLockedToast = useMemo(
    () => createToastThrottler(t("writing.agentLockedNoteEdit")),
    [t],
  );

  const handleContextMenu = useCallback(
    (id: string, type: "category" | "note", position: { x: number; y: number }, title: string) => {
      setContextMenuPos(position);
      setContextMenuTarget({ id, type, title });
    },
    [],
  );

  const handleCloseContextMenu = useCallback(() => {
    setContextMenuPos(null);
    setContextMenuTarget(null);
  }, []);

  const handleRename = useCallback(() => {
    if (!contextMenuTarget) return;
    setRenamingId(`${contextMenuTarget.type}:${contextMenuTarget.id}`);
    handleCloseContextMenu();
  }, [contextMenuTarget, handleCloseContextMenu]);

  const handleRenameConfirm = useCallback(
    async (id: string, type: "category" | "note", newTitle: string) => {
      setRenamingId(null);
      if (type === "note") {
        await updateNoteMutation.mutateAsync({ noteId: id, data: { title: newTitle } });
        toast.success(t("writing.noteRenamed"));
      } else {
        await updateCategoryMutation.mutateAsync({ categoryId: id, data: { title: newTitle } });
      }
    },
    [updateNoteMutation, updateCategoryMutation, t],
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.type === "note") {
        await deleteNoteMutation.mutateAsync(deleteTarget.id);
      } else {
        await deleteCategoryMutation.mutateAsync(deleteTarget.id);
      }
      setDeleteDialogOpen(false);
      setDeleteTarget(null);
    } catch {
      // handled by mutation
    }
  }, [deleteTarget, deleteNoteMutation, deleteCategoryMutation]);

  const handleNewNote = useCallback(
    async (categoryId?: string) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      const note = await createNoteMutation.mutateAsync({
        title: untitledDocumentLabel,
        categoryId,
      });
      setSelectedCategoryId(null);
      setCurrentNoteId(note.id);
      onNoteSelect(note.id, note.title);
    },
    [createNoteMutation, isAgentLocked, onNoteSelect, showLockedToast, untitledDocumentLabel],
  );

  const handleNewCategory = useCallback(async () => {
    if (isAgentLocked) {
      showLockedToast();
      return;
    }
    await createCategoryMutation.mutateAsync({
      title: t("writing.untitledCategory"),
    });
  }, [createCategoryMutation, isAgentLocked, showLockedToast, t]);

  const handleNoteSelect = useCallback(
    (noteId: string, title: string) => {
      setSelectedCategoryId(null);
      setCurrentNoteId(noteId);
      onNoteSelect(noteId, title);
    },
    [onNoteSelect],
  );

  const handleCategorySelect = useCallback((categoryId: string) => {
    setCurrentNoteId(null);
    setSelectedCategoryId(categoryId);
  }, []);

  const handleOpenInNewTab = useCallback(() => {
    if (!contextMenuTarget || contextMenuTarget.type !== "note") return;
    const target = contextMenuTarget;
    handleCloseContextMenu();
    onNoteSelect(target.id, target.title);
  }, [contextMenuTarget, handleCloseContextMenu, onNoteSelect]);

  const handleAddToConversation = useCallback(() => {
    if (!contextMenuTarget) return;
    const target = contextMenuTarget;
    handleCloseContextMenu();
    if (!onAddToConversation) return;
    const label = target.title.trim() || untitledDocumentLabel;
    if (target.type === "note") {
      onAddToConversation(buildNoteMentionTag({ noteId: target.id, label }));
    } else {
      onAddToConversation(buildNoteCategoryMentionTag({ categoryId: target.id, label }));
    }
  }, [contextMenuTarget, handleCloseContextMenu, onAddToConversation, untitledDocumentLabel]);

  const handleDuplicate = useCallback(async () => {
    if (!contextMenuTarget || contextMenuTarget.type !== "note") return;
    if (isAgentLocked) {
      showLockedToast();
      handleCloseContextMenu();
      return;
    }
    const target = contextMenuTarget;
    handleCloseContextMenu();
    try {
      const newNote = await duplicateNoteMutation.mutateAsync(target.id);
      setSelectedCategoryId(null);
      setCurrentNoteId(newNote.id);
      onNoteSelect(newNote.id, newNote.title);
    } catch {
      // handled by mutation
    }
  }, [
    contextMenuTarget,
    duplicateNoteMutation,
    handleCloseContextMenu,
    isAgentLocked,
    onNoteSelect,
    showLockedToast,
  ]);

  const handleToggleLock = useCallback(async () => {
    if (!contextMenuTarget || contextMenuTarget.type !== "note") return;
    const note = findNoteInTree(data, contextMenuTarget.id);
    if (!note) {
      handleCloseContextMenu();
      return;
    }
    handleCloseContextMenu();
    await toggleLockMutation.mutateAsync({ noteId: note.id, isLocked: !note.isLocked });
  }, [contextMenuTarget, data, handleCloseContextMenu, toggleLockMutation]);

  const handleSetAgentVisibility = useCallback(
    (noteId: string, visibility: NoteAgentVisibility) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      const note = findNoteInTree(data, noteId);
      if (!note || note.isLocked) return;
      void updateNoteMutation.mutateAsync({
        noteId,
        data: {
          agentVisibility: visibility,
        },
      });
    },
    [data, isAgentLocked, showLockedToast, updateNoteMutation],
  );

  const handleMove = useCallback(
    async (itemId: string, kind: "category" | "note", targetCategoryId: string | null) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      if (kind === "category" && targetCategoryId !== null) return;
      try {
        await moveMutation.mutateAsync({ kind, itemId, targetCategoryId });
      } catch {
        // handled by mutation
      }
    },
    [isAgentLocked, moveMutation, showLockedToast],
  );

  const handleManualMove = useCallback(
    async (direction: -1 | 1) => {
      if (!contextMenuTarget || !data) return;
      if (isAgentLocked) {
        showLockedToast();
        handleCloseContextMenu();
        return;
      }
      const siblings = resolveSiblingOrder(data, contextMenuTarget);
      if (!siblings) return;
      const targetIndex = siblings.index + direction;
      if (targetIndex < 0 || targetIndex >= siblings.orderedItems.length) return;
      const orderedItems = [...siblings.orderedItems];
      const [movedItem] = orderedItems.splice(siblings.index, 1);
      orderedItems.splice(targetIndex, 0, movedItem!);
      handleCloseContextMenu();
      try {
        await reorderMutation.mutateAsync({
          parentId: siblings.parentId,
          orderedItems,
        });
      } catch {
        // handled by mutation
      }
    },
    [
      contextMenuTarget,
      data,
      handleCloseContextMenu,
      isAgentLocked,
      reorderMutation,
      showLockedToast,
    ],
  );

  const contextMenuItems = useMemo<ContextMenuItem[]>(() => {
    if (!contextMenuTarget) return [];
    const items: ContextMenuItem[] = [];
    const siblingOrder =
      sortMode === "manual" && data ? resolveSiblingOrder(data, contextMenuTarget) : null;
    const targetNote =
      contextMenuTarget.type === "note" ? findNoteInTree(data, contextMenuTarget.id) : undefined;
    const targetIsLocked = targetNote?.isLocked === true;

    if (contextMenuTarget.type === "note") {
      items.push({
        id: "openInNewTab",
        label: t("chapterMenu.openInNewTab"),
        icon: ExternalLink,
        onClick: handleOpenInNewTab,
      });
    }

    if (sortMode === "manual")
      items.push({
        id: "sort",
        label: t("writing.sort"),
        onClick: () => {},
        children: [
          {
            id: "moveUp",
            label: t("chapterMenu.moveUp"),
            icon: ArrowUp,
            disabled: targetIsLocked || !siblingOrder || siblingOrder.index <= 0,
            onClick: () => void handleManualMove(-1),
          },
          {
            id: "moveDown",
            label: t("chapterMenu.moveDown"),
            icon: ArrowDown,
            disabled:
              targetIsLocked ||
              !siblingOrder ||
              siblingOrder.index >= siblingOrder.orderedItems.length - 1,
            onClick: () => void handleManualMove(1),
          },
        ],
      });

    if (contextMenuTarget.type === "category")
      items.push({
        id: "create",
        label: t(isOutline ? "writing.newOutline" : "writing.newNote"),
        icon: FilePlus,
        onClick: () => {
          void handleNewNote(contextMenuTarget.id);
          handleCloseContextMenu();
        },
      });
    if (contextMenuTarget.type === "note") {
      items.push({
        id: "move",
        label: t("projectNavigation.moveTo"),
        disabled: targetIsLocked || !data?.categories.length,
        onClick: () => {},
        children: [null, ...(data?.categories ?? [])].map((folder) => ({
          id: `move:${folder?.id ?? "root"}`,
          label: folder?.title ?? t("projectNavigation.moveToRoot"),
          disabled: targetIsLocked || (targetNote?.categoryId ?? null) === (folder?.id ?? null),
          onClick: () => {
            if ((targetNote?.categoryId ?? null) === (folder?.id ?? null)) return;
            void handleMove(contextMenuTarget.id, "note", folder?.id ?? null);
            handleCloseContextMenu();
          },
        })),
      });
    }
    if (contextMenuTarget.type === "category")
      items.push({
        id: "description",
        label: t("volume.menu.editDescription"),
        icon: Pencil,
        onClick: () => {
          setDescriptionTarget(contextMenuTarget.id);
          setFolderDescription(
            data?.categories.find((folder) => folder.id === contextMenuTarget.id)?.description ??
              "",
          );
        },
      });

    items.push({
      id: "addToConversation",
      label: t("chapterMenu.addToConversation"),
      icon: AtSign,
      disabled: !onAddToConversation,
      onClick: handleAddToConversation,
    });

    if (contextMenuTarget.type === "note") {
      items.push({
        id: "duplicate",
        label: t("chapterMenu.duplicate"),
        icon: Copy,
        onClick: () => void handleDuplicate(),
      });
    }

    items.push({
      id: "rename",
      label: t("chapterMenu.rename"),
      icon: Pencil,
      disabled: targetIsLocked,
      onClick: handleRename,
    });

    if (contextMenuTarget.type === "note") {
      const note = targetNote;
      if (note) {
        items.push({
          id: "toggleLock",
          label: note.isLocked ? t("writing.noteUnlock") : t("writing.noteLock"),
          icon: note.isLocked ? Unlock : Lock,
          onClick: () => void handleToggleLock(),
        });
      }
    }

    items.push({
      id: "delete",
      label: t("chapterMenu.delete"),
      icon: Trash2,
      danger: true,
      disabled: targetIsLocked,
      onClick: () => {
        setDeleteTarget(contextMenuTarget);
        setDeleteDialogOpen(true);
        handleCloseContextMenu();
      },
    });

    const order = [
      "openInNewTab",
      "addToConversation",
      "create",
      "rename",
      "duplicate",
      "move",
      "sort",
      "description",
      "toggleLock",
      "delete",
    ];
    items.sort((a, b) => {
      const rank = (id: string) => (order.includes(id) ? order.indexOf(id) : order.length - 1);
      return rank(a.id) - rank(b.id);
    });
    return items;
  }, [
    contextMenuTarget,
    data,
    handleAddToConversation,
    handleNewNote,
    handleMove,
    isOutline,
    handleCloseContextMenu,
    handleDuplicate,
    handleOpenInNewTab,
    handleManualMove,
    handleRename,
    handleToggleLock,
    onAddToConversation,
    sortMode,
    t,
  ]);

  const handleContentSearchToggle = useCallback(() => {
    setContentSearchExpanded((prev) => {
      if (prev) {
        setContentSearchOpen(false);
        return false;
      }
      return true;
    });
    if (!contentSearchExpanded && contentSearchQuery.trim()) {
      setContentSearchOpen(true);
    }
  }, [contentSearchExpanded, contentSearchQuery]);

  const handleContentSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setContentSearchQuery(e.target.value);
    if (e.target.value.trim()) {
      setContentSearchOpen(true);
    }
  }, []);

  const handleContentSearchFocus = useCallback(() => {
    if (contentSearchQuery.trim()) {
      setContentSearchOpen(true);
    }
  }, [contentSearchQuery]);

  const handleContentSearchBlur = useCallback(() => {
    if (!contentSearchQuery.trim()) {
      setContentSearchExpanded(false);
    }
  }, [contentSearchQuery]);

  const handlePopoverOpenChange = useCallback((open: boolean) => {
    setContentSearchOpen(open);
    if (!open) {
      setContentSearchExpanded(false);
    }
  }, []);

  useEffect(() => {
    if (contentSearchExpanded && searchContainerRef.current) {
      const input = searchContainerRef.current.querySelector("input");
      input?.focus();
    }
  }, [contentSearchExpanded]);

  const handleNavigateToNote = useCallback(
    (noteId: string) => {
      setSelectedCategoryId(null);
      setCurrentNoteId(noteId);
      const title = findNoteTitleInTree(data, noteId);
      onNoteSelect(noteId, title);
    },
    [data, onNoteSelect],
  );

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <ProjectNavToolbar
        search={
          <Box
            ref={searchContainerRef}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 0,
              height: "var(--space-6)",
              paddingRight: contentSearchExpanded ? "var(--space-2)" : 0,
              border: "1px solid transparent",
              borderColor: contentSearchExpanded ? "var(--gray-a7)" : "transparent",
              borderRadius: "max(var(--radius-2), var(--radius-full))",
              background: contentSearchExpanded ? "var(--color-surface)" : "transparent",
              flex: contentSearchExpanded ? 1 : undefined,
              minWidth: 0,
              position: "relative",
              transition:
                "border-color 0.15s ease, background 0.15s ease, padding-right 0.15s ease",
            }}
          >
            <NoteSearchPopover
              projectId={projectId}
              documentType={documentType}
              query={contentSearchQuery}
              open={contentSearchOpen}
              onOpenChange={handlePopoverOpenChange}
              onNavigateToNote={handleNavigateToNote}
            >
              <Box
                style={{
                  position: "absolute",
                  inset: 0,
                  pointerEvents: "none",
                }}
              />
            </NoteSearchPopover>
            <IconButton
              variant="ghost"
              size="2"
              onClick={contentSearchExpanded ? undefined : handleContentSearchToggle}
              style={{
                flexShrink: 0,
                opacity: contentSearchExpanded ? 0.5 : 1,
                transition: "opacity 0.15s ease",
                cursor: contentSearchExpanded ? "default" : undefined,
              }}
            >
              <Search size={16} />
            </IconButton>
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{
                width: contentSearchExpanded ? "100%" : 0,
                opacity: contentSearchExpanded ? 1 : 0,
              }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              style={{ overflow: "hidden" }}
            >
              {contentSearchExpanded && (
                <input
                  type="text"
                  placeholder={t("writing.contentSearchPlaceholder")}
                  value={contentSearchQuery}
                  onChange={handleContentSearchChange}
                  onFocus={handleContentSearchFocus}
                  onBlur={handleContentSearchBlur}
                  style={{
                    width: "100%",
                    border: "none",
                    outline: "none",
                    background: "transparent",
                    fontSize: "var(--font-size-base)",
                    lineHeight: "var(--line-height-2)",
                    color: "var(--gray-12)",
                    padding: 0,
                  }}
                />
              )}
            </motion.div>
          </Box>
        }
        sort={
          contentSearchExpanded ? null : (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <IconButton
                  variant="ghost"
                  size="2"
                  aria-label={t("writing.sort")}
                >
                  <ArrowUpDown size={16} />
                </IconButton>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content align="end">
                <DropdownMenu.CheckboxItem
                  checked={sortMode === "manual"}
                  onCheckedChange={() => setSortMode("manual")}
                >
                  {t("writing.sortManual")}
                </DropdownMenu.CheckboxItem>
                <DropdownMenu.CheckboxItem
                  checked={sortMode === "title"}
                  onCheckedChange={() => setSortMode("title")}
                >
                  {t("writing.sortTitle")}
                </DropdownMenu.CheckboxItem>
                <DropdownMenu.CheckboxItem
                  checked={sortMode === "updated"}
                  onCheckedChange={() => setSortMode("updated")}
                >
                  {t("writing.sortUpdated")}
                </DropdownMenu.CheckboxItem>
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          )
        }
        create={
          contentSearchExpanded ? null : (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <IconButton
                  variant="ghost"
                  size="2"
                  aria-label={t("common.create")}
                >
                  <Plus size={16} />
                </IconButton>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content align="end">
                <DropdownMenu.Item onClick={() => void handleNewNote()}>
                  <FilePlus size={16} />
                  {t(isOutline ? "writing.newOutline" : "writing.newNote")}
                </DropdownMenu.Item>
                <DropdownMenu.Item onClick={() => void handleNewCategory()}>
                  <FolderPlus size={16} />
                  {t("writing.newCategory")}
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          )
        }
      />

      <NoteFolderList
        data={data}
        emptyLabel={t(isOutline ? "writing.emptyOutlines" : "writing.emptyNotes")}
        onNoteSelect={handleNoteSelect}
        onCategorySelect={handleCategorySelect}
        currentNoteId={currentNoteId}
        selectedCategoryId={selectedCategoryId}
        renamingId={renamingId}
        onRenameConfirm={handleRenameConfirm}
        onRenameCancel={() => setRenamingId(null)}
        onContextMenu={handleContextMenu}
        onMove={handleMove}
        onReorder={async (parentId, orderedItems) => {
          if (isAgentLocked) {
            showLockedToast();
            return;
          }
          await reorderMutation.mutateAsync({ parentId, orderedItems });
        }}
        onSetAgentVisibility={handleSetAgentVisibility}
        isAgentLocked={isAgentLocked}
        sortMode={sortMode}
      />

      <Dialog.Root
        open={descriptionTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDescriptionTarget(null);
        }}
      >
        <Dialog.Content style={{ maxWidth: 400 }}>
          <Dialog.Title>{t("volume.menu.editDescription")}</Dialog.Title>
          <TextArea
            value={folderDescription}
            onChange={(e) => setFolderDescription(e.target.value)}
          />
          <Flex
            justify="end"
            gap="3"
            mt="4"
          >
            <Dialog.Close>
              <Button variant="soft">{t("common.cancel")}</Button>
            </Dialog.Close>
            <Button
              disabled={isAgentLocked || updateCategoryMutation.isPending}
              onClick={async () => {
                if (!descriptionTarget) return;
                await updateCategoryMutation.mutateAsync({
                  categoryId: descriptionTarget,
                  data: { description: folderDescription || null },
                });
                setDescriptionTarget(null);
              }}
            >
              {t("common.confirm")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      <ContextMenu
        position={contextMenuPos}
        items={contextMenuItems}
        onClose={handleCloseContextMenu}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open);
          if (!open) setDeleteTarget(null);
        }}
        title={t("chapterMenu.delete")}
        description={
          deleteTarget?.type === "category"
            ? t("projectNavigation.deleteFolderConfirm")
            : (deleteTarget?.title ?? "")
        }
        onConfirm={() => void handleDeleteConfirm()}
        loading={deleteNoteMutation.isPending || deleteCategoryMutation.isPending}
      />
    </div>
  );
}

function findNoteInTree(
  data: NoteTreeResponse | undefined,
  noteId: string,
):
  | {
      id: string;
      categoryId: string | null;
      isLocked: boolean;
      agentVisibility: string;
    }
  | undefined {
  if (!data) return undefined;
  const note = [...data.rootNotes, ...data.categories.flatMap((folder) => folder.notes)].find(
    (note) => note.id === noteId,
  );
  if (!note) return undefined;
  return {
    id: note.id,
    categoryId: note.categoryId,
    isLocked: note.isLocked,
    agentVisibility: note.agentVisibility,
  };
}

function resolveSiblingOrder(
  data: NoteTreeResponse,
  target: { id: string; type: "category" | "note" },
): {
  parentId: string | null;
  orderedItems: Array<{ id: string; kind: "category" | "note" }>;
  index: number;
} | null {
  const note =
    target.type === "note"
      ? [...data.rootNotes, ...data.categories.flatMap((folder) => folder.notes)].find(
          (note) => note.id === target.id,
        )
      : undefined;
  const parentId = note?.categoryId ?? null;
  const folder =
    parentId === null ? undefined : data.categories.find((folder) => folder.id === parentId);
  const siblings = target.type === "category" ? data.categories : (folder?.notes ?? data.rootNotes);
  const items = [...siblings]
    .sort((left, right) => left.order - right.order)
    .map((item) => ({ id: item.id, kind: target.type }));
  // The old reorder endpoint expects every root record; keep that shape only at this boundary.
  if (parentId === null)
    items.push(
      ...(target.type === "category" ? data.rootNotes : data.categories).map((item) => ({
        id: item.id,
        kind: target.type === "category" ? ("note" as const) : ("category" as const),
      })),
    );
  const index = items.findIndex((item) => item.id === target.id && item.kind === target.type);
  return index < 0 ? null : { parentId, orderedItems: items, index };
}

function findNoteTitleInTree(data: NoteTreeResponse | undefined, noteId: string): string {
  if (!data) return "";
  return (
    [...data.rootNotes, ...data.categories.flatMap((folder) => folder.notes)].find(
      (note) => note.id === noteId,
    )?.title ?? ""
  );
}
