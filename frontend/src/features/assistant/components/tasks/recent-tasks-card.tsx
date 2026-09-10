/**
 * Recent Tasks Card
 *
 * 悬浮的最近任务卡片组件
 */

import { Box, Button, Flex, Text } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

import type { TaskListItem } from "@/lib/task.types";

import "./recent-tasks-card.css";

import { TaskList } from "./task-list";

interface RecentTasksCardProps {
  tasks: TaskListItem[];
  hasRecentTasks: boolean;
  onTaskClick: (task: TaskListItem) => void;
  onToggleFavorite: (taskId: string, isFavorited: boolean) => void;
  onRenameTask: (taskId: string, title: string) => Promise<void>;
  onViewAll: () => void;
}

export function RecentTasksCard({
  tasks,
  hasRecentTasks,
  onTaskClick,
  onToggleFavorite,
  onRenameTask,
  onViewAll,
}: RecentTasksCardProps) {
  const { t } = useTranslation();

  return (
    <Flex
      align="center"
      justify="center"
      className="recent-tasks-container"
    >
      {/* 悬浮的最近任务卡片 */}
      <Box
        className={
          hasRecentTasks ? "recent-tasks-content recent-tasks-card" : "recent-tasks-content"
        }
      >
        {hasRecentTasks ? (
          <>
            {/* 标题栏 */}
            <Flex
              justify="between"
              align="center"
              className="recent-tasks-card-header"
            >
              <Text
                size="2"
                weight="medium"
              >
                {t("writing.aiSidebar.recentTasks")}
              </Text>
              <Button
                size="1"
                variant="ghost"
                onClick={onViewAll}
              >
                {t("writing.aiSidebar.viewAll")}
              </Button>
            </Flex>

            {/* 任务列表 */}
            <TaskList
              tasks={tasks}
              onTaskClick={onTaskClick}
              onToggleFavorite={onToggleFavorite}
              onRenameTask={onRenameTask}
            />
          </>
        ) : (
          // 无任务提示
          <Flex
            align="center"
            justify="center"
            direction="column"
            gap="2"
            className="recent-tasks-empty"
          >
            <Text size="2">{t("writing.aiSidebar.noTasks")}</Text>
          </Flex>
        )}
      </Box>
    </Flex>
  );
}
