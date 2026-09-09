import { Box, Flex, Text, Dialog, Button, Skeleton, IconButton, Tooltip } from "@radix-ui/themes";
/**
 * World Info Page
 *
 * 世界书主页面，按项目展示对应世界书条目与编辑器。
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { List } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router";

import { useAppShell } from "@/app/app-shell-context";
import { PanelLayoutLoading } from "@/components";
import { toast } from "@/components/toast";
import { AssistantSidebarHost } from "@/features/app-shell/components/assistant-sidebar-host";

import "./world-info-page.css";

import { MobileAppSidebarTrigger } from "@/features/app-shell/components/mobile-app-sidebar-trigger";
import type { AssistantSidebarState } from "@/features/assistant";
import { buildWorldInfoEntryMentionTag } from "@/features/assistant/lib/mention-text";
import { moveProjectFolderItem } from "@/features/project-folders/lib/project-folder-api";
import { ProjectNavShell } from "@/features/project-navigation/components/project-nav-shell";
import { fetchProjects } from "@/features/projects/lib/project-api";
import { WorkspaceLayout } from "@/features/workspace/components/workspace-layout";
import { WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { useWorkspace } from "@/features/workspace/hooks/use-workspace";
import { getPreference, setPreference } from "@/lib/local-db";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";
import type {
  WorldInfoEntry,
  WorldInfoEntryBrief,
  WorldInfoEntryBriefListResponse,
} from "@/lib/world-info.types";

import { EntryEditor } from "../components/entry-editor";
import { EntryList } from "../components/entry-list";
import { ImportWorldInfoDialog } from "../components/import-world-info-dialog";
import {
  batchDeleteWorldInfoEntries,
  batchToggleWorldInfoEntries,
  createWorldInfoEntry,
  deleteWorldInfoEntry,
  fetchWorldInfoByProject,
  fetchWorldInfoEntries,
  fetchWorldInfoEntry,
  moveWorldInfoEntry,
  updateWorldInfoEntry,
} from "../lib/world-info-api";
import { useWorldInfoStore } from "../store/use-world-info-store";
import {
  mergeWorldInfoEntryOrder,
  updateWorldInfoEntryBrief,
  updateWorldInfoEntryBriefs,
} from "./world-info-entry-cache";

const LAST_PROJECT_KEY = "worldInfo.lastProjectId";
const MotionBox = motion.create(Box);
const MOBILE_SIDEBAR_WIDTH = 320;

function generateUniqueEntryName(baseName: string, entries: WorldInfoEntryBrief[]): string {
  const normalizedName = baseName.trim();
  const existingNames = new Set(entries.map((entry) => entry.name));
  if (!existingNames.has(normalizedName)) return normalizedName;

  let counter = 1;
  while (existingNames.has(`${normalizedName} (${counter})`)) {
    counter += 1;
  }
  return `${normalizedName} (${counter})`;
}

export function WorldInfoPage() {
  const { t } = useTranslation();
  const { projectId: projectIdFromRoute } = useParams<{ projectId: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { isMobile } = useAppShell();

  const {
    currentWorldInfoId,
    currentProjectId,
    setCurrentProject,
    setCurrentWorldInfo,
    setCurrentEntry: setLegacyEntry,
    sidebarOpen,
    setSidebarOpen,
    setFromWriting,
  } = useWorldInfoStore();

  const workspace = useWorkspace(currentProjectId, "world");
  const currentEntryId = workspace.selectedId;
  const setCurrentEntry = workspace.select;
  const activeWorkspaceTabId = workspace.activeTab?.id;
  const workspaceStore = workspace.store;
  const handleWorkspaceScroll = useCallback(
    (top: number) => {
      if (activeWorkspaceTabId)
        workspaceStore.getState().updateTabScrollPosition(activeWorkspaceTabId, top);
    },
    [activeWorkspaceTabId, workspaceStore],
  );
  useEffect(() => {
    setLegacyEntry(currentEntryId);
  }, [currentEntryId, setLegacyEntry]);

  // 删除确认对话框状态
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [entryToDelete, setEntryToDelete] = useState<WorldInfoEntryBrief | null>(null);

  // 排序状态
  type SortField = "order" | "uid" | "tokenCount" | "name";
  type SortDirection = "asc" | "desc";
  const [sortField, setSortField] = useState<SortField>("order");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [isCreatingEntry, setIsCreatingEntry] = useState(false);
  const [scrollToLine, setScrollToLine] = useState<number | null>(null);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [assistantState, setAssistantState] = useState<AssistantSidebarState>({
    agentStatus: "idle",
    isAgentRunning: false,
  });

  // 从 URL 参数初始化状态
  useEffect(() => {
    const projectId = projectIdFromRoute ?? searchParams.get("projectId");
    const from = searchParams.get("from");

    if (from === "writing" && projectId) {
      setFromWriting(true, projectId);
    }
  }, [projectIdFromRoute, searchParams, setFromWriting]);

  const { data: projectsData } = useQuery({
    queryKey: ["projects", "world-info-page"],
    queryFn: () => fetchProjects({ page: 1, pageSize: 100 }),
  });

  const projects = useMemo(() => projectsData?.items ?? [], [projectsData?.items]);
  const projectIdFromUrl = projectIdFromRoute ?? searchParams.get("projectId");

  useEffect(() => {
    const initProject = async () => {
      if (projects.length === 0) return;
      const cachedProjectId = await getPreference(LAST_PROJECT_KEY);
      const routeProjectId =
        projectIdFromRoute && projects.some((project) => project.id === projectIdFromRoute)
          ? projectIdFromRoute
          : null;
      if (routeProjectId) {
        if (currentProjectId !== routeProjectId) setCurrentProject(routeProjectId);
        return;
      }
      if (currentProjectId) return;
      const nextProjectId =
        (projectIdFromUrl && projects.some((project) => project.id === projectIdFromUrl)
          ? projectIdFromUrl
          : null) ??
        (cachedProjectId && projects.some((project) => project.id === cachedProjectId)
          ? cachedProjectId
          : null) ??
        projects[0]?.id ??
        null;
      setCurrentProject(nextProjectId);
    };

    void initProject();
  }, [currentProjectId, projectIdFromRoute, projectIdFromUrl, projects, setCurrentProject]);

  useEffect(() => {
    if (currentProjectId) void setPreference(LAST_PROJECT_KEY, currentProjectId);
  }, [currentProjectId]);

  const { data: projectWorldInfo } = useQuery({
    queryKey: projectDataQueryKeys.worldInfo.byProject(currentProjectId),
    queryFn: () => fetchWorldInfoByProject(currentProjectId!),
    enabled: !!currentProjectId,
  });

  useEffect(() => {
    setCurrentWorldInfo(projectWorldInfo?.id ?? null);
  }, [projectWorldInfo?.id, setCurrentWorldInfo]);

  useEffect(() => {
    if (!currentProjectId) {
      setCurrentWorldInfo(null);
      setCurrentEntry(null);
    }
  }, [currentProjectId, setCurrentEntry, setCurrentWorldInfo]);

  // 获取条目列表（轻量，不含 content）
  const { data: entriesData, isLoading: entriesLoading } = useQuery({
    queryKey: projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
    queryFn: () => fetchWorldInfoEntries(currentWorldInfoId!),
    enabled: !!currentWorldInfoId,
    staleTime: 0,
  });

  // 获取当前选中条目的完整数据
  const { data: selectedEntry, isLoading: isEntryLoading } = useQuery({
    queryKey: projectDataQueryKeys.worldInfo.entryDetail(currentEntryId),
    queryFn: () => fetchWorldInfoEntry(currentEntryId!),
    enabled: !!currentEntryId,
    staleTime: 0,
  });

  const entries = useMemo(() => entriesData?.items ?? [], [entriesData?.items]);

  useEffect(() => {
    if (
      !workspace.ready ||
      !entriesData ||
      !projectWorldInfo ||
      projectWorldInfo.id !== currentWorldInfoId
    )
      return;
    workspace.store.getState().syncTabs(
      entries.map((item) => ({ id: item.id, title: item.name })),
      "note",
    );
  }, [
    entries,
    entriesData,
    workspace.ready,
    workspace.store,
    workspace.tabs,
    projectWorldInfo,
    currentWorldInfoId,
  ]);

  /** 从完整条目提取轻量字段，用于更新列表缓存 */
  const extractBrief = useCallback(
    (entry: WorldInfoEntry): WorldInfoEntryBrief => ({
      id: entry.id,
      worldInfoId: entry.worldInfoId,
      folderId: entry.folderId,
      uid: entry.uid,
      name: entry.name,
      section: entry.section,
      order: entry.order,
      tokenCount: entry.tokenCount,
      agentVisibility: entry.agentVisibility,
      createdAt: entry.createdAt,
      updatedAt: entry.updatedAt,
    }),
    [],
  );

  const removeEntryCaches = useCallback(
    async (worldInfoId: string, entryIds: string[]) => {
      const deletedEntryIds = new Set(entryIds);
      await queryClient.cancelQueries({
        queryKey: projectDataQueryKeys.worldInfo.entries(worldInfoId),
        exact: true,
      });
      await Promise.all(
        entryIds.map((entryId) =>
          queryClient.cancelQueries({
            queryKey: projectDataQueryKeys.worldInfo.entryDetail(entryId),
            exact: true,
          }),
        ),
      );
      queryClient.setQueryData(
        projectDataQueryKeys.worldInfo.entries(worldInfoId),
        (oldData: WorldInfoEntryBriefListResponse | undefined) => {
          if (!oldData) return oldData;
          const items = oldData.items.filter((entry) => !deletedEntryIds.has(entry.id));
          if (items.length === oldData.items.length) return oldData;
          return {
            ...oldData,
            items,
            total: oldData.total - (oldData.items.length - items.length),
          };
        },
      );
      entryIds.forEach((entryId) => {
        queryClient.removeQueries({
          queryKey: projectDataQueryKeys.worldInfo.entryDetail(entryId),
          exact: true,
        });
      });
    },
    [queryClient],
  );

  // 创建条目
  const createEntryMutation = useMutation({
    mutationFn: async ({ name, folderId }: { name: string; folderId?: string }) => {
      const entry = await createWorldInfoEntry(currentWorldInfoId!, { name });
      if (folderId) {
        await moveProjectFolderItem(currentProjectId!, "world", entry.id, folderId);
        entry.folderId = folderId;
      }
      return entry;
    },
    onSuccess: (newEntry) => {
      const brief = extractBrief(newEntry);
      queryClient.setQueryData(
        projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
        (oldData: WorldInfoEntryBriefListResponse | undefined) => {
          if (!oldData) {
            return {
              items: [brief],
              total: 1,
            };
          }

          return {
            ...oldData,
            items: [...oldData.items, brief],
            total: oldData.total + 1,
          };
        },
      );
      queryClient.setQueryData(projectDataQueryKeys.worldInfo.entryDetail(newEntry.id), newEntry);
      setCurrentEntry(newEntry.id);
    },
    onError: () => {
      toast.error(t("worldInfo.createFailed"));
    },
    onSettled: () => {
      setIsCreatingEntry(false);
    },
  });

  // 切换条目启用状态
  const toggleEntryMutation = useMutation({
    mutationFn: ({ entryId, agentVisibility }: { entryId: string; agentVisibility: string }) =>
      updateWorldInfoEntry(entryId, { agentVisibility }),
    mutationKey: ["world-info-entry-toggle", currentWorldInfoId],
    scope: { id: `world-info-entry-state-${currentWorldInfoId ?? ""}` },
    onMutate: async ({ entryId, agentVisibility }) => {
      const queryKey = projectDataQueryKeys.worldInfo.entries(currentWorldInfoId);
      await queryClient.cancelQueries({ queryKey });
      const previousEntries = queryClient.getQueryData<WorldInfoEntryBriefListResponse>(queryKey);

      queryClient.setQueryData(queryKey, (data: WorldInfoEntryBriefListResponse | undefined) =>
        updateWorldInfoEntryBrief(data, entryId, (entry) => ({
          ...entry,
          agentVisibility,
        })),
      );

      return { previousEntries, queryKey };
    },
    onSuccess: (updatedEntry, _entryId, context) => {
      toast.success(t("worldInfo.entryStatusUpdated"));
      const brief = extractBrief(updatedEntry);
      queryClient.setQueryData(
        context.queryKey,
        (oldData: WorldInfoEntryBriefListResponse | undefined) => {
          return updateWorldInfoEntryBrief(oldData, updatedEntry.id, () => brief);
        },
      );
      queryClient.setQueryData(
        projectDataQueryKeys.worldInfo.entryDetail(updatedEntry.id),
        updatedEntry,
      );
    },
    onError: (_error, _entryId, context) => {
      toast.error(t("worldInfo.entryStatusUpdateFailed"));
      if (context?.previousEntries) {
        queryClient.setQueryData(context.queryKey, context.previousEntries);
      }
    },
    onSettled: (_data, _error, _entryId, context) =>
      context ? queryClient.invalidateQueries({ queryKey: context.queryKey }) : undefined,
  });

  // 删除条目
  const deleteEntryMutation = useMutation({
    mutationFn: (entryId: string) => deleteWorldInfoEntry(entryId),
    onSuccess: async (_data, entryId) => {
      if (!currentWorldInfoId) return;
      workspaceStore.getState().removeTabsByReference("note", entryId);
      await removeEntryCaches(currentWorldInfoId, [entryId]);
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
      });
      toast.success(t("worldInfo.entryDeleted"));
      setEntryToDelete(null);
      setDeleteDialogOpen(false);
    },
    onError: () => {
      toast.error(t("worldInfo.deleteFailed"));
      setDeleteDialogOpen(false);
    },
  });

  /** 处理创建条目 */
  const handleCreateEntry = useCallback(
    (folderId?: string) => {
      if (currentWorldInfoId) {
        const name = generateUniqueEntryName(t("worldInfo.newEntry"), entries);
        setCurrentEntry(null);
        setIsCreatingEntry(true);
        createEntryMutation.mutate({ name, folderId });
      }
    },
    [currentWorldInfoId, createEntryMutation, entries, setCurrentEntry, t],
  );

  /** 处理选择条目 */
  const handleSelectEntry = useCallback(
    (entryId: string) => {
      setCurrentEntry(entryId);
      setSidebarOpen(false);
    },
    [setCurrentEntry, setSidebarOpen],
  );

  /** 处理切换条目启用状态 */
  const handleToggleEntry = useCallback(
    (entryId: string, agentVisibility: string) => {
      toggleEntryMutation.mutate({ entryId, agentVisibility });
    },
    [toggleEntryMutation],
  );

  /** 处理删除条目确认 */
  const handleDeleteEntry = useCallback((entry: WorldInfoEntryBrief) => {
    setEntryToDelete(entry);
    setDeleteDialogOpen(true);
  }, []);

  /** 确认删除 */
  const handleConfirmDelete = useCallback(() => {
    if (entryToDelete) {
      deleteEntryMutation.mutate(entryToDelete.id);
    }
  }, [entryToDelete, deleteEntryMutation]);

  /** 乐观更新条目顺序 */
  const handleReorderEntries = useCallback(
    (reorderedEntries: WorldInfoEntryBrief[]) => {
      queryClient.setQueryData(
        projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
        (oldData: WorldInfoEntryBriefListResponse | undefined) => {
          if (!oldData) {
            return {
              items: reorderedEntries,
              total: reorderedEntries.length,
            };
          }
          return {
            ...oldData,
            items: mergeWorldInfoEntryOrder(oldData, reorderedEntries)?.items ?? oldData.items,
          };
        },
      );
    },
    [currentWorldInfoId, queryClient],
  );

  /** 保存单条拖拽排序 */
  const handleSaveDragOrder = useCallback(
    async (entryId: string, newOrder: number) => {
      try {
        await moveWorldInfoEntry(entryId, newOrder);
        toast.success(t("worldInfo.entryOrderUpdated"));
      } catch (error) {
        console.error("Failed to save drag order:", error);
        toast.error(t("worldInfo.entryOrderUpdateFailed"));
        queryClient.invalidateQueries({
          queryKey: projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
        });
      }
    },
    [currentWorldInfoId, queryClient, t],
  );

  /** 处理排序切换 */
  const handleSortChange = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDirection("asc");
      }
    },
    [sortField],
  );

  /** 将条目置顶，本质为一次排序操作 */
  const handlePinEntry = useCallback(
    (entry: WorldInfoEntryBrief) => {
      const orderedEntries = [...entries].sort((a, b) => a.order - b.order);
      const currentIndex = orderedEntries.findIndex((item) => item.id === entry.id);
      if (currentIndex <= 0) return;

      const pinnedEntries = [
        orderedEntries[currentIndex],
        ...orderedEntries.slice(0, currentIndex),
        ...orderedEntries.slice(currentIndex + 1),
      ].map((item, index) => ({
        ...item,
        order: index + 1,
      }));

      handleReorderEntries(pinnedEntries);
      void handleSaveDragOrder(entry.id, 1);
    },
    [entries, handleReorderEntries, handleSaveDragOrder],
  );

  /** 批量删除条目 */
  const handleBatchDelete = useCallback(
    async (entryIds: string[]) => {
      if (!currentWorldInfoId) return;
      try {
        const count = await batchDeleteWorldInfoEntries(currentWorldInfoId, entryIds);
        entryIds.forEach((id) => workspaceStore.getState().removeTabsByReference("note", id));
        await removeEntryCaches(currentWorldInfoId, entryIds);
        queryClient.invalidateQueries({
          queryKey: projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
        });
        toast.success(t("worldInfo.batchDeleted", { count }));
      } catch {
        toast.error(t("worldInfo.deleteFailed"));
      }
    },
    [currentWorldInfoId, queryClient, removeEntryCaches, workspaceStore, t],
  );

  const batchToggleMutation = useMutation({
    mutationFn: ({ entryIds, agentVisibility }: { entryIds: string[]; agentVisibility: string }) =>
      batchToggleWorldInfoEntries(currentWorldInfoId!, entryIds, agentVisibility),
    mutationKey: ["world-info-entry-batch-toggle", currentWorldInfoId],
    scope: { id: `world-info-entry-state-${currentWorldInfoId ?? ""}` },
    onMutate: async ({ entryIds, agentVisibility }) => {
      const queryKey = projectDataQueryKeys.worldInfo.entries(currentWorldInfoId);
      await queryClient.cancelQueries({ queryKey });
      const previousEntries = queryClient.getQueryData<WorldInfoEntryBriefListResponse>(queryKey);

      queryClient.setQueryData(queryKey, (data: WorldInfoEntryBriefListResponse | undefined) =>
        updateWorldInfoEntryBriefs(data, entryIds, (entry) => ({ ...entry, agentVisibility })),
      );

      return { previousEntries, queryKey };
    },
    onSuccess: (count) => {
      toast.success(t("worldInfo.batchToggled", { count }));
    },
    onError: (_error, _variables, context) => {
      toast.error(t("worldInfo.entryStatusUpdateFailed"));
      if (context?.previousEntries) {
        queryClient.setQueryData(context.queryKey, context.previousEntries);
      }
    },
    onSettled: (_data, _error, _variables, context) =>
      context ? queryClient.invalidateQueries({ queryKey: context.queryKey }) : undefined,
  });

  /** 批量切换条目开关 */
  const handleBatchToggle = useCallback(
    (entryIds: string[], agentVisibility: string) => {
      if (!currentWorldInfoId) return;
      batchToggleMutation.mutate({ entryIds, agentVisibility });
    },
    [batchToggleMutation, currentWorldInfoId],
  );

  /** 处理从搜索面板导航到匹配行 */
  const handleNavigateToMatch = useCallback(
    (entryId: string, lineNumber: number) => {
      setCurrentEntry(entryId);
      setScrollToLine(lineNumber);
    },
    [setCurrentEntry],
  );

  /** 滚动完成后清除 */
  const handleScrollComplete = useCallback(() => {
    setScrollToLine(null);
  }, []);

  // 当前选中的条目（从详情查询获取完整数据）
  // selectedEntry 来自 useQuery，已在上方声明

  const isAgentLocked = Boolean(currentProjectId && assistantState.isAgentRunning);

  // 侧边栏内容
  const sidebarContent = currentProjectId ? (
    <EntryList
      projectId={currentProjectId}
      onImport={() => setImportDialogOpen(true)}
      entries={entries}
      onCreateEntry={handleCreateEntry}
      onSelectEntry={handleSelectEntry}
      onToggleEntry={handleToggleEntry}
      onDeleteEntry={handleDeleteEntry}
      onPinEntry={handlePinEntry}
      onReorderEntries={handleReorderEntries}
      onSaveDragOrder={handleSaveDragOrder}
      isLoading={entriesLoading}
      sortField={sortField}
      sortDirection={sortDirection}
      onSortChange={handleSortChange}
      onBatchDelete={handleBatchDelete}
      onBatchToggle={handleBatchToggle}
      onNavigateToMatch={handleNavigateToMatch}
    />
  ) : (
    <Flex
      align="center"
      justify="center"
      height="100%"
      p="4"
    >
      <Text
        size="2"
        color="gray"
        align="center"
      >
        {t("worldInfo.noProject")}
      </Text>
    </Flex>
  );

  const agentSidebarContent =
    currentProjectId && (selectedEntry || isMobile) ? (
      <AssistantSidebarHost
        projectId={currentProjectId}
        preferredAgentKey="discuss"
        initialComposerMarkup={
          selectedEntry
            ? buildWorldInfoEntryMentionTag({
                worldInfoEntryId: selectedEntry.id,
                label: selectedEntry.name,
              })
            : undefined
        }
        replaceComposerWithInitialMarkup
        onStateChange={setAssistantState}
        isMobileOverlay={isMobile}
      />
    ) : (
      <Flex
        align="center"
        justify="center"
        height="100%"
        p="4"
      >
        <Text
          size="2"
          color="gray"
          align="center"
        >
          {t("worldInfo.selectEntryToDiscuss")}
        </Text>
      </Flex>
    );

  const rawEditorContent = isCreatingEntry ? (
    <Box p="4">
      <Flex
        direction="column"
        gap="4"
        style={{ maxWidth: 800, margin: "0 auto" }}
      >
        <Skeleton
          width="120px"
          height="14px"
        />
        <Skeleton
          width="100%"
          height="36px"
        />
        <Flex gap="4">
          <Skeleton
            style={{ flex: 1 }}
            height="36px"
          />
          <Skeleton
            style={{ flex: 1 }}
            height="36px"
          />
        </Flex>
        <Skeleton
          width="100%"
          height="200px"
        />
        <Skeleton
          width="100%"
          height="80px"
        />
      </Flex>
    </Box>
  ) : currentEntryId && selectedEntry ? (
    <EntryEditor
      projectId={currentProjectId ?? undefined}
      scrollTop={workspace.activeTab?.scrollTop ?? 0}
      onScrollPositionChange={handleWorkspaceScroll}
      key={selectedEntry.id}
      entry={selectedEntry}
      worldInfoId={currentWorldInfoId!}
      entries={entries}
      scrollToLine={scrollToLine}
      onScrollComplete={handleScrollComplete}
      isAgentLocked={isAgentLocked}
    />
  ) : currentEntryId && isEntryLoading ? (
    <Box p="4">
      <Flex
        direction="column"
        gap="4"
        style={{ maxWidth: 800, margin: "0 auto" }}
      >
        <Skeleton
          width="120px"
          height="14px"
        />
        <Skeleton
          width="100%"
          height="36px"
        />
        <Flex gap="4">
          <Skeleton
            style={{ flex: 1 }}
            height="36px"
          />
          <Skeleton
            style={{ flex: 1 }}
            height="36px"
          />
        </Flex>
        <Skeleton
          width="100%"
          height="200px"
        />
        <Skeleton
          width="100%"
          height="80px"
        />
      </Flex>
    </Box>
  ) : (
    <Flex
      align="center"
      justify="center"
      height="100%"
      direction="column"
      gap="2"
    >
      <Text
        size="3"
        color="gray"
      >
        {t("worldInfo.selectEntry")}
      </Text>
    </Flex>
  );

  const editorContent = (
    <WorkspaceShell
      projectId={currentProjectId}
      store={workspace.store}
      emptyLabel="从左侧选择或新建条目"
    >
      {rawEditorContent}
    </WorkspaceShell>
  );

  return (
    <Flex
      direction="column"
      style={{
        height: "100%",
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      <Flex
        direction="column"
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        <Flex
          direction="column"
          style={{ height: "100%", minHeight: 0 }}
        >
          {!isMobile && currentProjectId ? (
            <Flex style={{ height: "100%", minWidth: 0 }}>
              <ProjectNavShell>{sidebarContent}</ProjectNavShell>
              <WorkspaceLayout assistant={<>{agentSidebarContent}</>}>
                {editorContent}
              </WorkspaceLayout>
            </Flex>
          ) : currentProjectId && isMobile ? (
            <Flex className="world-info-page-mobile-layout">
              <Box className="world-info-page-editor-shell world-info-page-editor-shell--mobile">
                <Flex
                  align="center"
                  justify="between"
                  px="3"
                  py="2"
                  className="world-info-page-mobile-topbar"
                >
                  <Flex
                    align="center"
                    gap="1"
                  >
                    <MobileAppSidebarTrigger />
                    <Tooltip content={t("worldInfo.entries")}>
                      <IconButton
                        variant="ghost"
                        size="2"
                        aria-label={t("worldInfo.entries")}
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                      >
                        <List size={18} />
                      </IconButton>
                    </Tooltip>
                  </Flex>
                </Flex>

                <Box
                  data-scroll-container
                  className="world-info-page-content-fill"
                >
                  {editorContent}
                </Box>

                <motion.div
                  initial={false}
                  animate={{ opacity: sidebarOpen ? 1 : 0 }}
                  transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                  onClick={() => setSidebarOpen(false)}
                  className="world-info-page-mobile-sidebar-backdrop"
                  style={{ pointerEvents: sidebarOpen ? "auto" : "none" }}
                />

                <MotionBox
                  initial={false}
                  animate={{ x: sidebarOpen ? 0 : -MOBILE_SIDEBAR_WIDTH }}
                  transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                  className="world-info-page-mobile-sidebar-sheet"
                  style={{
                    width: MOBILE_SIDEBAR_WIDTH,
                    minWidth: MOBILE_SIDEBAR_WIDTH,
                    pointerEvents: sidebarOpen ? "auto" : "none",
                  }}
                >
                  {sidebarContent}
                </MotionBox>
              </Box>
            </Flex>
          ) : currentProjectId ? (
            <PanelLayoutLoading />
          ) : (
            <Flex
              align="center"
              justify="center"
              height="100%"
              direction="column"
              gap="2"
            >
              <Text
                size="3"
                weight="medium"
              >
                {t("worldInfo.noProject")}
              </Text>
              <Text
                size="2"
                color="gray"
              >
                {t("worldInfo.noProjectHint")}
              </Text>
            </Flex>
          )}
        </Flex>
      </Flex>

      {isMobile && currentProjectId ? agentSidebarContent : null}

      <ImportWorldInfoDialog
        open={importDialogOpen}
        worldInfoId={currentWorldInfoId}
        onOpenChange={setImportDialogOpen}
        onSuccess={() => {
          queryClient.invalidateQueries({
            queryKey: projectDataQueryKeys.worldInfo.entries(currentWorldInfoId),
          });
        }}
      />

      {/* 删除确认对话框 */}
      <Dialog.Root
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
      >
        <Dialog.Content style={{ maxWidth: 400 }}>
          <Dialog.Title>{t("worldInfo.deleteEntry")}</Dialog.Title>
          <Dialog.Description
            size="2"
            mb="4"
          >
            {t("worldInfo.deleteEntryConfirm", { name: entryToDelete?.name })}
          </Dialog.Description>
          <Flex
            gap="3"
            justify="end"
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
              variant="solid"
              color="red"
              onClick={handleConfirmDelete}
              disabled={deleteEntryMutation.isPending}
            >
              {t("common.delete")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </Flex>
  );
}
