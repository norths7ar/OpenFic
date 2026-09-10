import { useQuery } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { useTranslation } from "react-i18next";

import { apiClient } from "@/lib/api-transport";

import { PlanTodoList } from "./message-blocks/tools/plan/plan-tool-message";
import type { PlanTodoPayload } from "./message-blocks/tools/shared/tool-message-utils";

import "./session-task-list.css";

export function SessionTaskList({
  sessionId,
  isRunning,
}: {
  sessionId: string;
  isRunning: boolean;
}) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["agent-task-list", sessionId, isRunning],
    queryFn: async () => {
      const response = await apiClient.get<{ todos: PlanTodoPayload[] }>(
        `/agent/sessions/${sessionId}/todos`,
      );
      return response.data.todos;
    },
    enabled: Boolean(sessionId),
    refetchInterval: isRunning ? 5000 : false,
  });
  if (!data?.length) return null;
  const completed = data.filter((todo) => todo.status === "completed").length;
  const current = data.find((todo) => todo.status === "in_progress");
  return (
    <details className="agent-session-task-list">
      <summary>
        <ListChecks
          size={15}
          aria-hidden="true"
        />
        <span>{t("assistant.taskList.title")}</span>
        <span className="agent-session-task-list-progress">
          {completed}/{data.length}
        </span>
        {current ? (
          <span className="agent-session-task-list-current">{current.content}</span>
        ) : null}
      </summary>
      <div className="agent-session-task-list-content">
        <PlanTodoList todos={data} />
      </div>
    </details>
  );
}
