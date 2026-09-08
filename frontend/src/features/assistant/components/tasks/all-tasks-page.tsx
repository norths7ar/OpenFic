import {
  Box,
  Button,
  Dialog,
  DropdownMenu,
  Flex,
  Text,
  IconButton,
  TextField,
} from "@radix-ui/themes";
/**
 * All Tasks Page
 *
 * 查看全部任务页面组件。
 */
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import {
  ArrowLeft,
  ArrowUpDown,
  FolderInput,
  FilePlus,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Plus,
  Star,
  Trash2,
  ListX,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog, Spinner } from "@/components";
import { ContextMenu, type ContextMenuItem } from "@/components/context-menu";
import {
  useProjectFolderMutations,
  useProjectFolders,
} from "@/features/project-folders/hooks/use-project-folders";
import type { ProjectFolder } from "@/features/project-folders/lib/project-folder-api";
import { ProjectFolderGroups } from "@/features/project-navigation/components/project-folder-groups";
import { ProjectNavItemRow } from "@/features/project-navigation/components/project-nav-item-row";
import { ProjectNavSearch } from "@/features/project-navigation/components/project-nav-search";
import { ProjectNavToolbar } from "@/features/project-navigation/components/project-nav-toolbar";
import type { TaskListItem } from "@/lib/task.types";

import { useTasks, useUpdateTask, useDeleteTask, useDeleteAllTasks } from "../../hooks/use-tasks";
import { TaskRenameInput } from "./task-rename-input";

interface AllTasksPageProps {
  projectId: string;
  onBack: () => void;
  onTaskClick: (task: TaskListItem) => void;
  activeTaskId?: string | null;
  showBack?: boolean;
  title?: string;
  onNew?: (folderId?: string) => void;
  newLabel?: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
}

export function AllTasksPage({
  projectId,
  onBack,
  onTaskClick,
  activeTaskId = null,
  showBack = true,
  title,
  onNew,
  newLabel,
  searchPlaceholder,
  emptyLabel,
}: AllTasksPageProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchExpanded, setSearchExpanded] = useState(false);
  const [itemMenu, setItemMenu] = useState<{ task: TaskListItem; x: number; y: number } | null>(
    null,
  );
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingTask, setDeletingTask] = useState<TaskListItem | null>(null);
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [savingTaskId, setSavingTaskId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"updated" | "title">("updated");
  const { data: folders = [] } = useProjectFolders(projectId, "discussion");
  const folderMutations = useProjectFolderMutations(projectId, "discussion");
  const [folderDialog, setFolderDialog] = useState<{
    mode: "create" | "rename";
    folder?: ProjectFolder;
  } | null>(null);
  const [folderTitle, setFolderTitle] = useState("");
  const [deletingFolderId, setDeletingFolderId] = useState<string | null>(null);
  const [folderDescription, setFolderDescription] = useState("");

  // 获取任务列表
  const { data, isLoading, refetch } = useTasks(projectId, {
    search: searchQuery || undefined,
  });
  const { data: allTasksData } = useTasks(projectId);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask(projectId);
  const deleteAllMutation = useDeleteAllTasks(projectId);

  // 格式化时间
  const formatTime = (dateString: string) => {
    try {
      return formatDistanceToNow(new Date(dateString), {
        addSuffix: true,
        locale: zhCN,
      });
    } catch {
      return dateString;
    }
  };

  const handleCancelEdit = () => {
    setEditingTaskId(null);
  };

  const handleCommitEdit = async (taskId: string, originalTitle: string, nextTitle: string) => {
    const trimmedTitle = nextTitle.trim();
    if (!trimmedTitle || trimmedTitle === originalTitle) {
      handleCancelEdit();
      return;
    }

    setSavingTaskId(taskId);
    try {
      await updateMutation.mutateAsync({
        taskId,
        data: { title: trimmedTitle },
      });
      handleCancelEdit();
    } finally {
      setSavingTaskId(null);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingTask) return;
    await deleteMutation.mutateAsync(deletingTask.id);
    setDeleteDialogOpen(false);
    setDeletingTask(null);
  };

  const handleConfirmDeleteAll = async () => {
    await deleteAllMutation.mutateAsync();
    setDeleteAllDialogOpen(false);
  };

  const tasks = [...(data?.items ?? [])].sort((left, right) =>
    sortBy === "title"
      ? left.title.localeCompare(right.title, "zh-CN")
      : right.updatedAt.localeCompare(left.updatedAt),
  );
  const allTasks = allTasksData?.items ?? [];
  const hasAnyTasks = allTasks.length > 0;
  const runningTaskCount = allTasks.filter((task) => task.isRunning).length;
  const deleteAllDescription =
    runningTaskCount > 0
      ? t("writing.aiSidebar.deleteAllTasksConfirmWithRunning", { count: runningTaskCount })
      : t("writing.aiSidebar.deleteAllTasksConfirm");
  const runningLabel = t("writing.aiSidebar.taskRunning");

  const menuTask = itemMenu ? tasks.find((task) => task.id === itemMenu.task.id) : undefined;
  const menuItems: ContextMenuItem[] = menuTask
    ? [
        {
          id: "rename",
          label: t("common.rename"),
          icon: Pencil,
          disabled: savingTaskId === menuTask.id,
          onClick: () => setEditingTaskId(menuTask.id),
        },
        {
          id: "move",
          label: t("projectNavigation.moveTo"),
          icon: FolderInput,
          disabled:
            folderMutations.moveItem.isPending || (folders.length === 0 && !menuTask.folderId),
          onClick: () => {},
          children: [{ id: "root", title: t("projectNavigation.root") }, ...folders].map(
            (folder) => {
              const folderId = folder.id === "root" ? null : folder.id;
              return {
                id: `move-${folder.id}`,
                label: folder.title,
                disabled: (menuTask.folderId ?? null) === folderId,
                onClick: () => {
                  if (
                    (menuTask.folderId ?? null) !== folderId &&
                    !folderMutations.moveItem.isPending
                  )
                    folderMutations.moveItem.mutate({ itemId: menuTask.id, folderId });
                },
              };
            },
          ),
        },
        {
          id: "favorite",
          label: t(
            menuTask.isFavorited ? "writing.aiSidebar.unfavorite" : "writing.aiSidebar.favorite",
          ),
          icon: Star,
          onClick: () =>
            updateMutation.mutate({
              taskId: menuTask.id,
              data: { is_favorited: !menuTask.isFavorited },
            }),
        },
        {
          id: "delete",
          label: t("common.delete"),
          icon: Trash2,
          danger: true,
          disabled: menuTask.isRunning,
          onClick: () => {
            setDeletingTask(menuTask);
            setDeleteDialogOpen(true);
          },
        },
      ]
    : [];
  return (
    <Box
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "var(--color-panel)",
      }}
    >
      <ProjectNavToolbar
        searchExpanded={searchExpanded}
        search={
          <Flex
            align="center"
            gap="1"
          >
            {showBack ? (
              <IconButton
                variant="ghost"
                size="2"
                onClick={onBack}
                aria-label={t("common.back")}
              >
                <ArrowLeft size={18} />
              </IconButton>
            ) : null}
            <ProjectNavSearch
              onExpandedChange={setSearchExpanded}
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder={searchPlaceholder ?? title ?? t("writing.aiSidebar.searchTasks")}
            />
          </Flex>
        }
        sort={
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <IconButton
                variant="ghost"
                size="2"
                aria-label={t("characters.sort")}
              >
                <ArrowUpDown size={16} />
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end">
              <DropdownMenu.CheckboxItem
                checked={sortBy === "updated"}
                onCheckedChange={() => setSortBy("updated")}
              >
                {t("characters.sortByUpdated")}
              </DropdownMenu.CheckboxItem>
              <DropdownMenu.CheckboxItem
                checked={sortBy === "title"}
                onCheckedChange={() => setSortBy("title")}
              >
                {t("characters.sortByName")}
              </DropdownMenu.CheckboxItem>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        }
        create={
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
              {onNew && (
                <DropdownMenu.Item onSelect={() => onNew()}>
                  <FilePlus size={16} />
                  {newLabel ?? t("assistant.newTask")}
                </DropdownMenu.Item>
              )}
              <DropdownMenu.Item
                onSelect={() => {
                  setFolderTitle("");
                  setFolderDescription("");
                  setFolderDialog({ mode: "create" });
                }}
              >
                <FolderPlus size={16} />
                {t("projectNavigation.newFolder")}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        }
        more={
          hasAnyTasks ? (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <IconButton
                  variant="ghost"
                  size="2"
                  aria-label={t("common.more")}
                >
                  <MoreHorizontal size={18} />
                </IconButton>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content align="end">
                {hasAnyTasks ? (
                  <DropdownMenu.Item
                    color="red"
                    onClick={() => setDeleteAllDialogOpen(true)}
                  >
                    <ListX size={16} />
                    {t("writing.aiSidebar.deleteAllTasks")}
                  </DropdownMenu.Item>
                ) : null}
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          ) : null
        }
      />

      {/* 任务列表 */}
      <Box
        style={{
          flex: 1,
          overflow: "auto",
        }}
      >
        {isLoading ? (
          <Flex
            align="center"
            justify="center"
            style={{ padding: "32px" }}
          >
            <Spinner size={18} />
          </Flex>
        ) : tasks.length === 0 && folders.length === 0 ? (
          <Flex
            align="center"
            justify="center"
            style={{ padding: "32px", color: "var(--gray-9)" }}
          >
            <Text size="2">
              {searchQuery
                ? t("writing.aiSidebar.noSearchResults")
                : (emptyLabel ?? t("writing.aiSidebar.noTasks"))}
            </Text>
          </Flex>
        ) : (
          <ProjectFolderGroups
            folders={folders}
            items={tasks}
            renderFolderMenu={(folder) => (
              <DropdownMenu.Root>
                <DropdownMenu.Trigger>
                  <IconButton
                    variant="ghost"
                    size="1"
                    aria-label={t("common.more")}
                  >
                    <MoreHorizontal size={14} />
                  </IconButton>
                </DropdownMenu.Trigger>
                <DropdownMenu.Content align="end">
                  {onNew && (
                    <DropdownMenu.Item onClick={() => onNew(folder.id)}>
                      {newLabel ?? t("assistant.newTask")}
                    </DropdownMenu.Item>
                  )}
                  <DropdownMenu.Item
                    onClick={() => {
                      setFolderTitle(folder.title);
                      setFolderDescription(folder.description ?? "");
                      setFolderDialog({ mode: "rename", folder });
                    }}
                  >
                    {t("common.rename")}
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    color="red"
                    onClick={() => setDeletingFolderId(folder.id)}
                  >
                    {t("common.delete")}
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>
            )}
            renderItem={(task) => (
              <ProjectNavItemRow
                key={task.id}
                selected={task.id === activeTaskId}
                onClick={() => {
                  if (editingTaskId !== task.id) onTaskClick(task);
                }}
                title={
                  editingTaskId === task.id ? (
                    <TaskRenameInput
                      key={task.id}
                      initialValue={task.title}
                      disabled={savingTaskId === task.id}
                      onConfirm={(newTitle) => handleCommitEdit(task.id, task.title, newTitle)}
                      onCancel={handleCancelEdit}
                    />
                  ) : (
                    task.title
                  )
                }
                status={
                  task.isRunning && (
                    <span
                      aria-label={runningLabel}
                      className="task-running-dot"
                      title={runningLabel}
                    />
                  )
                }
                metadata={formatTime(task.updatedAt)}
                actions={
                  <>
                    {task.isFavorited && (
                      <Star
                        size={14}
                        fill="currentColor"
                        color="var(--amber-9)"
                        aria-label={t("writing.aiSidebar.favorite")}
                      />
                    )}
                    <IconButton
                      variant="ghost"
                      size="1"
                      className="project-nav-item-more"
                      aria-label={t("common.more")}
                      onClick={(event) => {
                        event.stopPropagation();
                        const rect = event.currentTarget.getBoundingClientRect();
                        setItemMenu({ task, x: rect.left, y: rect.bottom });
                      }}
                    >
                      <MoreHorizontal size={14} />
                    </IconButton>
                  </>
                }
                onContextMenu={(event) => {
                  event.preventDefault();
                  setItemMenu({ task, x: event.clientX, y: event.clientY });
                }}
              />
            )}
          />
        )}
      </Box>

      <ContextMenu
        position={itemMenu}
        items={menuItems}
        onClose={() => setItemMenu(null)}
      />
      {/* 删除确认对话框 */}
      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        onConfirm={handleConfirmDelete}
        title={t("writing.aiSidebar.deleteTask")}
        description={t("writing.aiSidebar.deleteTaskConfirm", {
          title: deletingTask?.title ?? "",
        })}
        confirmText={t("common.delete")}
        confirmColor="red"
        loading={deleteMutation.isPending}
      />

      <ConfirmDialog
        open={deletingFolderId !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingFolderId(null);
        }}
        title={t("common.delete")}
        description={t("projectNavigation.deleteFolderConfirm")}
        onConfirm={() => {
          if (deletingFolderId) folderMutations.remove.mutate(deletingFolderId);
          setDeletingFolderId(null);
        }}
      />
      <Dialog.Root
        open={folderDialog !== null}
        onOpenChange={(open) => {
          if (!open) setFolderDialog(null);
        }}
      >
        <Dialog.Content style={{ maxWidth: 400 }}>
          <Dialog.Title>
            {t(
              folderDialog?.mode === "rename"
                ? "projectNavigation.renameFolder"
                : "projectNavigation.newFolder",
            )}
          </Dialog.Title>
          <TextField.Root
            value={folderTitle}
            onChange={(event) => setFolderTitle(event.target.value)}
            autoFocus
          />
          <textarea
            aria-label={t("volume.menu.editDescription")}
            placeholder={t("volume.menu.editDescription")}
            value={folderDescription}
            onChange={(event) => setFolderDescription(event.target.value)}
            style={{
              width: "100%",
              boxSizing: "border-box",
              marginTop: 12,
              minHeight: 70,
              background: "var(--color-background)",
              color: "var(--gray-12)",
            }}
          />
          <Flex
            gap="3"
            justify="end"
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
              onClick={() => {
                const nextTitle = folderTitle.trim();
                if (!nextTitle || !folderDialog) return;
                if (folderDialog.mode === "rename" && folderDialog.folder)
                  folderMutations.rename.mutate({
                    folderId: folderDialog.folder.id,
                    title: nextTitle,
                    description: folderDescription || null,
                  });
                else
                  folderMutations.create.mutate({
                    title: nextTitle,
                    description: folderDescription || null,
                  });
                setFolderDialog(null);
                setFolderTitle("");
                setFolderDescription("");
              }}
            >
              {t("common.confirm")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      {/* 删除全部确认对话框 */}
      <ConfirmDialog
        open={deleteAllDialogOpen}
        onOpenChange={setDeleteAllDialogOpen}
        onConfirm={handleConfirmDeleteAll}
        title={t("writing.aiSidebar.deleteAllTasks")}
        description={deleteAllDescription}
        confirmText={t("common.delete")}
        confirmColor="red"
        loading={deleteAllMutation.isPending}
      />
    </Box>
  );
}
