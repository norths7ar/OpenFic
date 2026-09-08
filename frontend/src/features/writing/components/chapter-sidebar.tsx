import { Box, Button, Dialog, Flex, TextArea } from "@radix-ui/themes";
import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";

import { ConfirmDialog, toast } from "@/components";
import { PROJECT_NAV_ROOT_ID } from "@/features/project-navigation/lib/project-nav-groups";
import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";
import { createToastThrottler } from "@/lib/ui-utils";

import {
  useCreateChapter,
  useUpdateChapter,
  useDeleteChapter,
  useMoveChapterToVolume,
} from "../hooks/use-chapters";
import {
  useCreateVolume,
  useDeleteVolume,
  useMoveVolume,
  useUpdateVolume,
  useVolumeTree,
} from "../hooks/use-volumes";
import { fetchChapter } from "../lib/chapter-volume-api";
import { useTabsStore } from "../store/use-tabs-store";
import { useWritingStore } from "../store/use-writing-store";
import { ChapterExportDialog } from "./chapter-export-dialog";
import {
  findVolumeIdForChapter,
  getInitialCurrentChapterVolumeIdToExpand,
  type GroupedVolumeListScrollRequest,
} from "./grouped-volume-list-focus";
import { SidebarToolbar } from "./sidebar-toolbar";
import { VolumeList } from "./volume-list";

interface ChapterSidebarProps {
  projectId: string;
  onChapterSelect: (chapterId: string, chapterTitle: string) => void;
  onAddToConversation?: (markup: string) => void;
  isAgentLocked?: boolean;
  compact?: boolean;
  initialCurrentChapterNavigationKey?: string | null;
  onOpenSummary?: () => void;
}

export function ChapterSidebar({
  projectId,
  onChapterSelect,
  onAddToConversation,
  isAgentLocked = false,
  compact = false,
  initialCurrentChapterNavigationKey = null,
  onOpenSummary,
}: ChapterSidebarProps) {
  const { t } = useTranslation();

  const { data, isLoading } = useVolumeTree(projectId);
  const createChapterMutation = useCreateChapter(projectId);
  const updateChapterMutation = useUpdateChapter();
  const deleteChapterMutation = useDeleteChapter(projectId);
  const moveChapterToVolumeMutation = useMoveChapterToVolume(projectId);
  const createVolumeMutation = useCreateVolume(projectId);
  const updateVolumeMutation = useUpdateVolume();
  const deleteVolumeMutation = useDeleteVolume(projectId);
  const moveVolumeMutation = useMoveVolume(projectId);

  const { openTab, tabs } = useTabsStore();
  const MAX_TABS = 10;

  const {
    currentChapterId,
    setCurrentChapter,
    expandedVolumeIds,
    hasHydratedExpandedVolumeIds,
    hasStoredExpandedVolumeIdsPreference,
    hydrateExpandedVolumeIds,
    setVolumeExpanded,
    toggleVolumeExpanded,
  } = useWritingStore(
    useShallow((state) => ({
      currentChapterId: state.currentChapterId,
      setCurrentChapter: state.setCurrentChapter,
      expandedVolumeIds: state.expandedVolumeIds,
      hasHydratedExpandedVolumeIds: state.hasHydratedExpandedVolumeIds,
      hasStoredExpandedVolumeIdsPreference: state.hasStoredExpandedVolumeIdsPreference,
      hydrateExpandedVolumeIds: state.hydrateExpandedVolumeIds,
      setVolumeExpanded: state.setVolumeExpanded,
      toggleVolumeExpanded: state.toggleVolumeExpanded,
    })),
  );

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingChapter, setDeletingChapter] = useState<ChapterListItem | null>(null);
  const [deletingVolume, setDeletingVolume] = useState<VolumeWithChapters | null>(null);
  const [renamingVolumeId, setRenamingVolumeId] = useState<string | null>(null);
  const [editingVolume, setEditingVolume] = useState<VolumeWithChapters | null>(null);
  const [editingVolumeDescription, setEditingVolumeDescription] = useState("");
  const [chapterExportOpen, setChapterExportOpen] = useState(false);
  const [localTitleOverrides, setLocalTitleOverrides] = useState<Record<string, string>>({});
  const [scrollRequest, setScrollRequest] = useState<GroupedVolumeListScrollRequest | null>(null);
  const defaultExpansionAppliedProjectRef = useRef<string | null>(null);
  const scrollRequestSequenceRef = useRef(0);
  const lastHandledInitialCurrentChapterNavigationKeyRef = useRef<string | null>(null);

  const showLockedToast = useMemo(
    () => createToastThrottler(t("writing.agentLockedChapterEdit")),
    [t],
  );

  useEffect(() => {
    void hydrateExpandedVolumeIds();
  }, [hydrateExpandedVolumeIds]);

  const volumes = useMemo(() => {
    const source = data?.volumes ?? [];
    if (Object.keys(localTitleOverrides).length === 0) return source;

    return source.map((volume) => ({
      ...volume,
      chapters: volume.chapters.map((chapter) => {
        const localTitle = localTitleOverrides[chapter.id];
        return localTitle && chapter.title !== localTitle
          ? { ...chapter, title: localTitle }
          : chapter;
      }),
    }));
  }, [data?.volumes, localTitleOverrides]);

  useEffect(() => {
    if (!hasHydratedExpandedVolumeIds || !volumes.length) return;
    if (defaultExpansionAppliedProjectRef.current === projectId) return;
    defaultExpansionAppliedProjectRef.current = projectId;
    if (hasStoredExpandedVolumeIdsPreference) return;
    if (expandedVolumeIds.size > 0) return;
    volumes.forEach((volume) => setVolumeExpanded(volume.id, true));
  }, [
    expandedVolumeIds.size,
    hasHydratedExpandedVolumeIds,
    hasStoredExpandedVolumeIdsPreference,
    projectId,
    setVolumeExpanded,
    volumes,
  ]);

  useEffect(() => {
    if (!hasHydratedExpandedVolumeIds || !initialCurrentChapterNavigationKey) {
      return;
    }

    if (
      lastHandledInitialCurrentChapterNavigationKeyRef.current ===
      initialCurrentChapterNavigationKey
    ) {
      return;
    }

    const volumeId = findVolumeIdForChapter(volumes, currentChapterId);
    if (!volumeId) {
      return;
    }

    lastHandledInitialCurrentChapterNavigationKeyRef.current = initialCurrentChapterNavigationKey;

    const targetVolumeId = getInitialCurrentChapterVolumeIdToExpand({
      initialNavigationKey: initialCurrentChapterNavigationKey,
      volumes,
      expandedVolumeIds,
      currentChapterId,
    });

    if (!targetVolumeId) {
      return;
    }

    setVolumeExpanded(targetVolumeId, true);
  }, [
    currentChapterId,
    expandedVolumeIds,
    hasHydratedExpandedVolumeIds,
    initialCurrentChapterNavigationKey,
    setVolumeExpanded,
    volumes,
  ]);

  const allChapters = useMemo(() => volumes.flatMap((volume) => volume.chapters), [volumes]);

  const createScrollRequestKey = useCallback((prefix: string, id: string) => {
    scrollRequestSequenceRef.current += 1;
    return `${prefix}:${id}:${scrollRequestSequenceRef.current}`;
  }, []);

  const createChapterInVolume = useCallback(
    async (volumeId: string) => {
      if (isAgentLocked) {
        showLockedToast();
        return null;
      }

      const newChapter = await createChapterMutation.mutateAsync({
        volumeId,
        title: t("writing.untitledChapter"),
      });
      setVolumeExpanded(volumeId, true);
      setScrollRequest({
        key: createScrollRequestKey("chapter", newChapter.id),
        type: "chapter",
        chapterId: newChapter.id,
      });
      setCurrentChapter(newChapter.id);
      onChapterSelect(newChapter.id, newChapter.title);
      return newChapter;
    },
    [
      createChapterMutation,
      isAgentLocked,
      onChapterSelect,
      setCurrentChapter,
      setVolumeExpanded,
      createScrollRequestKey,
      showLockedToast,
      t,
    ],
  );

  const handleCreateChapter = useCallback(async () => {
    await createChapterInVolume(PROJECT_NAV_ROOT_ID);
  }, [createChapterInVolume]);

  const handleCreateVolume = useCallback(async () => {
    if (isAgentLocked) {
      showLockedToast();
      return;
    }
    const volume = await createVolumeMutation.mutateAsync({
      title: t("volume.untitled"),
    });
    setVolumeExpanded(volume.id, true);
    setScrollRequest({
      key: createScrollRequestKey("volume", volume.id),
      type: "volume",
      volumeId: volume.id,
    });
  }, [
    createScrollRequestKey,
    createVolumeMutation,
    isAgentLocked,
    setVolumeExpanded,
    showLockedToast,
    t,
  ]);

  const handleChapterSelect = useCallback(
    (chapterId: string) => {
      const chapter = allChapters.find((item) => item.id === chapterId);
      setCurrentChapter(chapterId);
      onChapterSelect(chapterId, chapter?.title ?? "");
    },
    [allChapters, onChapterSelect, setCurrentChapter],
  );

  const handleOpenInNewTab = useCallback(
    (chapterId: string, title: string) => {
      if (tabs.length >= MAX_TABS) {
        // openTab 内部会处理满的情况
      }
      openTab(chapterId, title);
    },
    [openTab, tabs.length],
  );

  const handleDuplicate = useCallback(
    async (chapterId: string, title: string) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }

      try {
        const originalChapter = await fetchChapter(chapterId);
        const newChapter = await createChapterMutation.mutateAsync({
          volumeId: originalChapter.volumeId,
          title: `${title}-副本`,
          content: originalChapter.content,
          wordCount: originalChapter.wordCount,
        });
        setCurrentChapter(newChapter.id);
        onChapterSelect(newChapter.id, newChapter.title);
      } catch {
        // 错误处理由 mutation 处理
      }
    },
    [createChapterMutation, isAgentLocked, onChapterSelect, setCurrentChapter, showLockedToast],
  );

  const handleRenameChapter = useCallback(
    async (chapterId: string, newTitle: string) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }

      setLocalTitleOverrides((prev) => ({ ...prev, [chapterId]: newTitle }));

      try {
        await updateChapterMutation.mutateAsync({
          chapterId,
          data: { title: newTitle },
        });
      } catch {
        setLocalTitleOverrides((prev) => {
          const next = { ...prev };
          delete next[chapterId];
          return next;
        });
      }
    },
    [isAgentLocked, showLockedToast, updateChapterMutation],
  );

  const handleOpenDeleteChapter = useCallback(
    (chapter: ChapterListItem) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }

      setDeletingChapter(chapter);
      setDeletingVolume(null);
      setDeleteDialogOpen(true);
    },
    [isAgentLocked, showLockedToast],
  );

  const handleOpenDeleteVolume = useCallback(
    (volume: VolumeWithChapters) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      setDeletingVolume(volume);
      setDeletingChapter(null);
      setDeleteDialogOpen(true);
    },
    [isAgentLocked, showLockedToast],
  );

  const handleDeleteDialogChange = useCallback((open: boolean) => {
    setDeleteDialogOpen(open);
    if (!open) {
      setDeletingChapter(null);
      setDeletingVolume(null);
    }
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (deletingChapter) {
      try {
        await deleteChapterMutation.mutateAsync(deletingChapter.id);
        toast.success(t("writing.deleteChapterSuccess"));
        handleDeleteDialogChange(false);
      } catch {
        toast.error(t("writing.deleteChapterFailed"));
      }
      return;
    }

    if (deletingVolume) {
      try {
        await deleteVolumeMutation.mutateAsync({
          volumeId: deletingVolume.id,
          cascade: false,
        });
        toast.success(t("writing.deleteVolumeSuccess"));
        handleDeleteDialogChange(false);
      } catch {
        toast.error(t("writing.deleteVolumeFailed"));
      }
    }
  }, [
    deleteChapterMutation,
    deleteVolumeMutation,
    deletingChapter,
    deletingVolume,
    handleDeleteDialogChange,
    t,
  ]);

  const handleRenameVolume = useCallback(
    async (volumeId: string, title: string) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      setRenamingVolumeId(null);
      await updateVolumeMutation.mutateAsync({
        volumeId,
        data: { title },
      });
    },
    [isAgentLocked, showLockedToast, updateVolumeMutation],
  );

  const handleOpenDescriptionEditor = useCallback((volume: VolumeWithChapters) => {
    setEditingVolume(volume);
    setEditingVolumeDescription(volume.description ?? "");
  }, []);

  const handleSaveDescription = useCallback(async () => {
    if (!editingVolume) return;
    await updateVolumeMutation.mutateAsync({
      volumeId: editingVolume.id,
      data: { description: editingVolumeDescription.trim() || null },
    });
    setEditingVolume(null);
    setEditingVolumeDescription("");
  }, [editingVolume, editingVolumeDescription, updateVolumeMutation]);

  const handleMoveVolume = useCallback(
    async (volume: VolumeWithChapters, direction: -1 | 1) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      await moveVolumeMutation.mutateAsync({
        volumeId: volume.id,
        newOrder:
          volumes
            .filter((folder) => !folder.isRoot)
            .findIndex((folder) => folder.id === volume.id) +
          1 +
          direction,
      });
    },
    [isAgentLocked, moveVolumeMutation, showLockedToast, volumes],
  );

  const handleMoveChapter = useCallback(
    (chapter: ChapterListItem, volumeId: string) => {
      if (isAgentLocked) {
        showLockedToast();
        return;
      }
      if (volumeId === chapter.volumeId) return;
      moveChapterToVolumeMutation.mutate({ chapterId: chapter.id, volumeId });
      setVolumeExpanded(volumeId, true);
    },
    [isAgentLocked, showLockedToast, moveChapterToVolumeMutation, setVolumeExpanded],
  );

  return (
    <Box
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "var(--color-background)",
      }}
    >
      <SidebarToolbar
        onOpenSummary={onOpenSummary}
        projectId={projectId}
        onChapterSelect={handleChapterSelect}
        onCreateChapter={handleCreateChapter}
        onCreateVolume={handleCreateVolume}
        onExport={() => setChapterExportOpen(true)}
        isAgentLocked={isAgentLocked}
        onLockedAction={showLockedToast}
      />

      <VolumeList
        projectId={projectId}
        volumes={volumes}
        isLoading={isLoading}
        scrollRequest={scrollRequest}
        expandedVolumeIds={expandedVolumeIds}
        renamingVolumeId={renamingVolumeId}
        isAgentLocked={isAgentLocked}
        compact={compact}
        initialCurrentChapterNavigationKey={initialCurrentChapterNavigationKey}
        onToggleVolume={toggleVolumeExpanded}
        onStartRenameVolume={setRenamingVolumeId}
        onRenameVolume={handleRenameVolume}
        onCancelRenameVolume={() => setRenamingVolumeId(null)}
        onEditVolumeDescription={handleOpenDescriptionEditor}
        onCreateChapterInVolume={(volumeId) => void createChapterInVolume(volumeId)}
        onMoveVolumeUp={(volume) => void handleMoveVolume(volume, -1)}
        onMoveVolumeDown={(volume) => void handleMoveVolume(volume, 1)}
        onDeleteVolume={handleOpenDeleteVolume}
        onChapterSelect={handleChapterSelect}
        onOpenInNewTab={handleOpenInNewTab}
        onDuplicate={handleDuplicate}
        onRenameChapter={handleRenameChapter}
        onMoveChapterToVolume={handleMoveChapter}
        onDeleteChapter={handleOpenDeleteChapter}
        onAddToConversation={onAddToConversation}
        onLockedAction={showLockedToast}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={handleDeleteDialogChange}
        title={deletingVolume ? t("volume.menu.delete") : t("chapterMenu.delete")}
        description={
          deletingVolume
            ? deletingVolume.chapterCount > 0
              ? t("projectNavigation.deleteFolderKeepsItems")
              : t("volume.deleteConfirm")
            : (deletingChapter?.title ?? "")
        }
        onConfirm={handleConfirmDelete}
        loading={deleteChapterMutation.isPending || deleteVolumeMutation.isPending}
      />

      <ChapterExportDialog
        open={chapterExportOpen}
        onOpenChange={setChapterExportOpen}
        projectId={projectId}
        volumes={volumes}
      />

      <Dialog.Root
        open={Boolean(editingVolume)}
        onOpenChange={(open) => {
          if (!open) {
            setEditingVolume(null);
            setEditingVolumeDescription("");
          }
        }}
      >
        <Dialog.Content maxWidth="420px">
          <Dialog.Title>{t("volume.menu.editDescription")}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
          >
            {editingVolume?.title ?? t("volume.untitled")}
          </Dialog.Description>
          <TextArea
            mt="4"
            value={editingVolumeDescription}
            onChange={(event) => setEditingVolumeDescription(event.target.value)}
            resize="vertical"
            style={{ minHeight: 120 }}
          />
          <Flex
            justify="end"
            gap="3"
            mt="4"
          >
            <Dialog.Close>
              <Button
                variant="soft"
                color="gray"
              >
                {t("common.cancel")}
              </Button>
            </Dialog.Close>
            <Button
              loading={updateVolumeMutation.isPending}
              onClick={() => void handleSaveDescription()}
            >
              {t("common.confirm")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </Box>
  );
}
