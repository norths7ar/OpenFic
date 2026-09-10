import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ListChecks } from "lucide-react";
import { useId, useLayoutEffect, useRef, useState } from "react";
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
  const [expanded, setExpanded] = useState(false);
  const [moving, setMoving] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const previousSize = useRef<DOMRect | null>(null);
  const animationRef = useRef<Animation | null>(null);
  const contentId = useId();
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
  useLayoutEffect(() => {
    const shell = shellRef.current;
    const previous = previousSize.current;
    if (!shell || !previous) return;
    previousSize.current = null;
    // Measure once per opening, then keep the width stable while tasks update.
    shell.style.width = "";
    const target = shell.getBoundingClientRect();
    if (expanded) shell.style.width = `${target.width}px`;
    const animation = shell.animate(
      [
        { width: `${previous.width}px`, height: `${previous.height}px` },
        { width: `${target.width}px`, height: `${target.height}px` },
      ],
      {
        duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180,
        easing: "ease-in-out",
      },
    );
    animationRef.current = animation;
    animation.onfinish = () => setMoving(false);
    return () => {
      animation.onfinish = null;
      animation.cancel();
    };
  }, [expanded]);

  if (!data?.length) return null;
  const completed = data.filter((todo) => todo.status === "completed").length;
  return (
    <div className="agent-session-task-list-rail">
      <div
        ref={shellRef}
        className="agent-session-task-list"
        data-moving={moving}
      >
        <button
          type="button"
          aria-label={`${t("assistant.taskList.title")} ${completed}/${data.length}`}
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => {
            previousSize.current = shellRef.current?.getBoundingClientRect() ?? null;
            animationRef.current?.cancel();
            setMoving(true);
            setExpanded((value) => !value);
          }}
        >
          <ListChecks
            size={15}
            aria-hidden="true"
          />
          <span>{t("assistant.taskList.title")}</span>
          <span className="agent-session-task-list-progress">
            {completed}/{data.length}
          </span>
          <ChevronDown
            size={14}
            aria-hidden="true"
            style={{ transform: expanded ? "rotate(180deg)" : undefined }}
          />
        </button>
        <div
          id={contentId}
          className="agent-session-task-list-content"
          hidden={!expanded}
        >
          <PlanTodoList todos={data} />
        </div>
      </div>
    </div>
  );
}
