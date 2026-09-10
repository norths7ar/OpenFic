/**
 * Task List
 *
 * 任务列表组件，显示最近的任务。
 */

import { Box, Flex, Text, IconButton, Tooltip } from "@radix-ui/themes";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import { Pencil, Star, Clock } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { TaskListItem } from "@/lib/task.types";

import "./task-list.css";

import { TaskRenameInput } from "./task-rename-input";

interface TaskListProps {
  tasks: TaskListItem[];
  onTaskClick: (task: TaskListItem) => void;
  onToggleFavorite: (taskId: string, isFavorited: boolean) => void;
  onRenameTask: (taskId: string, title: string) => Promise<void>;
}

export function TaskList({ tasks, onTaskClick, onToggleFavorite, onRenameTask }: TaskListProps) {
  const { t } = useTranslation();
  const runningLabel = t("writing.aiSidebar.taskRunning");
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [savingTaskId, setSavingTaskId] = useState<string | null>(null);

  const handleStartEdit = (task: TaskListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingTaskId(task.id);
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
      await onRenameTask(taskId, trimmedTitle);
      handleCancelEdit();
    } finally {
      setSavingTaskId(null);
    }
  };

  const handleToggleFavorite = (task: TaskListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleFavorite(task.id, !task.isFavorited);
  };

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

  if (tasks.length === 0) {
    return (
      <Flex
        align="center"
        justify="center"
        className="task-list-empty"
      >
        <Text size="2">{t("writing.aiSidebar.noTasks")}</Text>
      </Flex>
    );
  }

  return (
    <Box>
      {tasks.map((task) => (
        <Box
          key={task.id}
          className="task-list-item"
          onClick={() => {
            if (editingTaskId !== task.id) onTaskClick(task);
          }}
        >
          <Flex
            align="center"
            gap="2"
            mb="2"
          >
            {editingTaskId === task.id ? (
              <Box className="task-list-rename">
                <TaskRenameInput
                  key={task.id}
                  initialValue={task.title}
                  disabled={savingTaskId === task.id}
                  onConfirm={(newTitle) => handleCommitEdit(task.id, task.title, newTitle)}
                  onCancel={handleCancelEdit}
                />
              </Box>
            ) : (
              <Text
                size="2"
                weight="medium"
                className="task-list-title"
              >
                {task.title}
              </Text>
            )}
            {task.isRunning && (
              <span
                aria-label={runningLabel}
                className="task-running-dot"
                title={runningLabel}
              />
            )}
          </Flex>

          {/* 底部栏 */}
          <Flex
            justify="between"
            align="center"
          >
            {/* 左侧：时间 */}
            <Flex
              align="center"
              gap="1"
              className="task-list-time"
            >
              <Clock size={12} />
              <Text size="1">{formatTime(task.updatedAt)}</Text>
            </Flex>

            {/* 右侧：操作按钮 */}
            <Flex
              align="center"
              gap="1"
            >
              <Tooltip content={t("common.edit")}>
                <IconButton
                  variant="ghost"
                  size="1"
                  onClick={(e) => handleStartEdit(task, e)}
                  disabled={savingTaskId === task.id}
                  className="task-list-action"
                >
                  <Pencil size={14} />
                </IconButton>
              </Tooltip>
              <Tooltip
                content={
                  task.isFavorited
                    ? t("writing.aiSidebar.unfavorite")
                    : t("writing.aiSidebar.favorite")
                }
              >
                <IconButton
                  variant="ghost"
                  size="1"
                  onClick={(e) => handleToggleFavorite(task, e)}
                  className="task-list-action task-list-favorite"
                  data-favorited={task.isFavorited}
                >
                  <Star
                    size={14}
                    className="task-list-favorite-icon"
                  />
                </IconButton>
              </Tooltip>
            </Flex>
          </Flex>
        </Box>
      ))}
    </Box>
  );
}
