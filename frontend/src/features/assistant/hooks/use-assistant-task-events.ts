import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import type { TaskListItem } from "@/lib/task.types";

import { subscribeBackgroundEvents } from "../lib/agent-runtime-api";

export function useAssistantTaskEvents(
  projectId: string,
  currentTaskId: string | null,
  setCurrentTaskTitle: (title: string) => void,
) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!projectId) return;
    const subscription = subscribeBackgroundEvents(
      projectId,
      (event) => {
        if (event.type === "task_title_updated" && event.task_id && event.title) {
          const taskId = event.task_id;
          const title = event.title;
          if (taskId === currentTaskId) setCurrentTaskTitle(title);
          queryClient.setQueriesData(
            { queryKey: ["tasks", projectId], exact: false },
            (current) => {
              if (!current || typeof current !== "object" || !("items" in current)) return current;
              const response = current as { items: TaskListItem[]; total: number };
              return {
                ...response,
                items: response.items.map((task) =>
                  task.id === taskId
                    ? { ...task, title, updatedAt: event.updated_at ?? task.updatedAt }
                    : task,
                ),
              };
            },
          );
          queryClient.setQueryData(["task", taskId], (current) => {
            if (!current || typeof current !== "object") return current;
            return {
              ...current,
              title,
              updatedAt: event.updated_at ?? (current as { updatedAt?: string }).updatedAt,
            };
          });
          return;
        }

        if (event.type === "task_run_status_updated" && event.task_id) {
          const taskId = event.task_id;
          const isRunning = event.is_running === true;
          queryClient.setQueryData(["task", taskId], (current) => {
            if (!current || typeof current !== "object") return current;
            return {
              ...current,
              isRunning,
              updatedAt: event.updated_at ?? (current as { updatedAt?: string }).updatedAt,
            };
          });
          void queryClient.invalidateQueries({
            queryKey: ["tasks", projectId],
            exact: false,
          });
        }
      },
      () => {
        console.warn("Background event stream disconnected");
      },
    );
    return () => subscription.close();
  }, [currentTaskId, projectId, queryClient, setCurrentTaskTitle]);
}
