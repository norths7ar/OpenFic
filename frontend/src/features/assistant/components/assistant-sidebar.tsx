import { Box, Flex, IconButton, Text } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, SquareArrowOutUpRight } from "lucide-react";
import {
  forwardRef,
  useState,
  useCallback,
  useRef,
  useEffect,
  useMemo,
  useImperativeHandle,
} from "react";
import { useTranslation } from "react-i18next";

import { useAppShell } from "@/app/app-shell-context";
import { ConfirmDialog, Spinner, toast, getModelValue } from "@/components";
import { AgentBrandIcon } from "@/components/agent-brand-icon";
import {
  appendMentionMarkup,
  replaceAutomaticMentionMarkup,
} from "@/features/assistant/lib/mention-text";
import { usePendingProjectChangeCount } from "@/features/pending-project-changes/hooks";
import { moveProjectFolderItem } from "@/features/project-folders/lib/project-folder-api";
import { ProjectNavShell } from "@/features/project-navigation/components/project-nav-shell";
import { fetchAgentDefinitions } from "@/features/settings/lib/agent-definitions-api";
import { fetchSettings, updateSettings } from "@/features/settings/lib/settings-api";
import { getAgentDisplayDescription, getAgentIconColor } from "@/lib/agent-branding";
import type {
  ActiveSubagentState,
  AgentForkResponse,
  AgentSessionCreateResponse,
  AgentMessage,
  ReasoningEffort,
  TokenUsageState,
} from "@/lib/agent.types";
import type { TaskListItem } from "@/lib/task.types";
import { useLlmModelOptions } from "@/lib/use-llm-model-options";

import { useAssistantTaskEvents } from "../hooks/use-assistant-task-events";
import { useSubagentSession } from "../hooks/use-subagent-session";
import { useSummarySendGuard } from "../hooks/use-summary-send-guard";
import { useTasks, useUpdateTask } from "../hooks/use-tasks";
import {
  createRestoredPendingAgentAttachments,
  type PendingAgentImageAttachment,
} from "../lib/agent-image-attachments";

import "./assistant-sidebar.css";

import {
  fetchActiveSubagents,
  fetchAgentSessionState,
  fetchTask,
  updateAgentKnowledgeScope,
} from "../lib/agent-runtime-api";
import { loadAgentTaskBundle } from "../lib/agent-task-bundle";
import {
  createConversationStackState,
  getCurrentConversationDescriptor,
  getCurrentSubagentSnapshot,
  openSubagentConversation,
  returnToPrimaryConversation,
  syncParentConversationState,
  type AssistantConversationStackState,
} from "../lib/assistant-conversation-state";
import {
  constrainReasoningEffort,
  getStoredAgentKey,
  getStoredModelId,
  getStoredReasoningEffort,
  isReasoningEffort,
  storeAgentKey,
  storeModelId,
  storeReasoningEffort,
} from "../lib/assistant-preferences";
import type { AssistantSidebarState } from "../lib/assistant-state.types";
import {
  applyTaskUsageDelta,
  applyTaskUsageSnapshot,
  buildTaskConversationUsage,
  createSessionTotalUsageState,
  createTokenUsageState,
  DEFAULT_CONTEXT_LENGTH,
  selectConversationUsage,
  type SessionTotalUsageState,
  type TaskUsagePayload,
} from "../lib/assistant-usage-state";
import type { AssistantView } from "../lib/assistant.types";
import type {
  SceneDraftApplyRequest,
  SceneDraftRequest,
  SceneDraftTarget,
} from "../lib/scene-draft";
import { formatSubagentDisplayLabel } from "../lib/subagent-display";
import { createPendingApprovalMessage } from "../lib/subagent-session-approval";
import { joinSubagentStatusStream, subscribeSubagentStatusEvents } from "../lib/subagent-socket";
import { buildAgentMessagesFromTaskMessages } from "../lib/task-message-agent-mapping";
import { AgentInput, AgentMessages, useAgentSidebar } from "./agent";
import { ActiveSubagentList } from "./agent/active-subagent-list";
import { AgentSpecialPanels } from "./agent/agent-special-panels";
import { getAgentSpecialPanels } from "./agent/agent-special-panels-state";
import { SessionTaskList } from "./agent/session-task-list";
import { AssistantProjectActions } from "./assistant-project-actions";
import { AssistantSessionHeader } from "./assistant-session-header";
import { AllTasksPage } from "./tasks/all-tasks-page";
import { RecentTasksCard } from "./tasks/recent-tasks-card";

interface AssistantSidebarProps {
  projectId: string;
  preferredAgentKey?: string;
  initialComposerMarkup?: string;
  replaceComposerWithInitialMarkup?: boolean;
  discussionWorkspace?: boolean;
  onStateChange?: (state: AssistantSidebarState) => void;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
  onApplySceneDraft?: (request: SceneDraftApplyRequest) => Promise<boolean>;
  onClose?: () => void;
  isMobileOverlay?: boolean;
}

export interface AssistantSidebarHandle {
  appendToComposer: (markup: string) => void;
  prepareSceneDraft: (request: SceneDraftRequest) => void;
}

function upsertActiveSubagent(
  items: ActiveSubagentState[],
  nextItem: ActiveSubagentState,
): ActiveSubagentState[] {
  const remaining = items.filter((item) => item.childRunId !== nextItem.childRunId);
  if (!nextItem.isActive) return remaining;
  return [...remaining, nextItem].sort((left, right) =>
    left.agentKey.localeCompare(right.agentKey),
  );
}

function getSubagentStatusLabel(
  status: ActiveSubagentState["status"] | "" | undefined,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (status === "queued") return t("writing.aiSidebar.subagentStatusQueued");
  if (status === "running") return t("writing.aiSidebar.subagentStatusRunning");
  if (status === "waiting_user") return t("writing.aiSidebar.subagentStatusWaitingUser");
  if (status === "completed") return t("writing.aiSidebar.subagentStatusCompleted");
  if (status === "error") return t("writing.aiSidebar.subagentStatusError");
  if (status === "cancelled") return t("writing.aiSidebar.subagentStatusCancelled");
  return t("writing.aiSidebar.subagentInactive");
}

export const AssistantSidebar = forwardRef<AssistantSidebarHandle, AssistantSidebarProps>(
  function AssistantSidebar(
    {
      projectId,
      preferredAgentKey,
      initialComposerMarkup,
      replaceComposerWithInitialMarkup = false,
      discussionWorkspace = false,
      onStateChange,
      onOpenMentionChapter,
      onApplySceneDraft,
      onClose,
      isMobileOverlay = false,
    }: AssistantSidebarProps,
    ref,
  ) {
    const { t } = useTranslation();
    const { data: pendingChanges } = usePendingProjectChangeCount(projectId);
    const pendingCount = pendingChanges?.count ?? 0;
    const { openSettings } = useAppShell();
    const queryClient = useQueryClient();

    const [selectedModelId, setSelectedModelId] = useState<string>(() => {
      return getStoredModelId();
    });
    const [selectedAgentKey, setSelectedAgentKey] = useState<string>(() => {
      return getStoredAgentKey();
    });
    const [conversationState, setConversationState] = useState<AssistantConversationStackState>(
      () => createConversationStackState(""),
    );
    const [activeSubagents, setActiveSubagents] = useState<ActiveSubagentState[]>([]);
    const [inputValue, setInputValue] = useState("");
    const [pendingAttachments, setPendingAttachments] = useState<PendingAgentImageAttachment[]>([]);
    const [view, setView] = useState<AssistantView>("tasks");
    const [isLoadingTask, setIsLoadingTask] = useState(false);
    const [currentTaskTitle, setCurrentTaskTitle] = useState<string>("");
    const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
    const [contextMode, setContextMode] = useState<"global" | "local">("local");
    const [isUpdatingScope, setIsUpdatingScope] = useState(false);
    const [sceneDraftTarget, setSceneDraftTarget] = useState<SceneDraftTarget | null>(null);
    const [sessionTotalUsage, setSessionTotalUsage] = useState<SessionTotalUsageState>(() =>
      createSessionTotalUsageState(),
    );
    const [conversationUsageBySession, setConversationUsageBySession] = useState<
      Record<string, TokenUsageState>
    >({});
    const [isMessagesAtBottom, setIsMessagesAtBottom] = useState(true);
    const handledPreferredAgentRef = useRef<string | null>(null);
    const handledInitialComposerMarkupRef = useRef<string | null>(null);
    const automaticComposerMarkupRef = useRef<string | null>(null);
    const scrollToBottomFnRef = useRef<(() => void) | null>(null);
    const prepareSceneDraftActionRef = useRef<(request: SceneDraftRequest) => void>(() => {});

    const { data: tasksData, refetch: refetchRecentTasks } = useTasks(projectId, { limit: 3 });
    const updateTaskMutation = useUpdateTask();

    const {
      options: llmModelOptions,
      isLoading: isModelsLoading,
      error: modelsError,
    } = useLlmModelOptions();

    const { data: agentDefinitions = [] } = useQuery({
      queryKey: ["agent-definitions"],
      queryFn: fetchAgentDefinitions,
      staleTime: 5 * 60 * 1000,
    });

    const primaryAgents = useMemo(
      () => agentDefinitions.filter((d) => d.kind === "primary" && d.enabled),
      [agentDefinitions],
    );

    const effectiveAgentKey = useMemo(() => {
      if (selectedAgentKey) {
        const matched = primaryAgents.find((d) => d.key === selectedAgentKey);
        if (matched) return matched.key;
      }
      const fallback = primaryAgents.find((d) => d.key === "build");
      if (fallback) return fallback.key;
      if (primaryAgents.length > 0) return primaryAgents[0].key;
      return "";
    }, [selectedAgentKey, primaryAgents]);

    const { data: settings } = useQuery({
      queryKey: ["settings"],
      queryFn: fetchSettings,
      staleTime: 5 * 60 * 1000,
    });

    const { mutate: toggleToolApprovalBypass, isPending: isTogglingToolApprovalBypass } =
      useMutation({
        mutationFn: async (enabled: boolean) =>
          updateSettings({
            agent_bypass_tool_approval: enabled,
          }),
        onSuccess: (savedSettings) => {
          queryClient.setQueryData(["settings"], savedSettings);
        },
        onError: () => {
          toast.error(t("writing.aiSidebar.toggleApprovalBypassFailed"));
        },
      });

    const effectiveModelId = useMemo(() => {
      if (
        selectedModelId &&
        llmModelOptions.some((model) => getModelValue(model) === selectedModelId)
      ) {
        return selectedModelId;
      }
      const defaultModelId = settings?.defaultModel;
      if (
        defaultModelId &&
        llmModelOptions.some((model) => getModelValue(model) === defaultModelId)
      ) {
        return defaultModelId;
      }
      if (llmModelOptions.length > 0) return getModelValue(llmModelOptions[0]);
      return "";
    }, [selectedModelId, llmModelOptions, settings?.defaultModel]);

    const currentModel = useMemo(
      () => llmModelOptions.find((model) => getModelValue(model) === effectiveModelId),
      [effectiveModelId, llmModelOptions],
    );
    const [deliveryMode, setDeliveryMode] = useState<"steer" | "queue">("steer");
    const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>(() =>
      constrainReasoningEffort(
        getStoredReasoningEffort(
          effectiveModelId,
          Boolean(currentModel?.reasoningEffortLevels?.length),
        ),
        currentModel?.reasoningEffortLevels,
      ),
    );
    const isToolApprovalBypassEnabled = settings?.agentBypassToolApproval ?? false;
    const agentSidebarRef = useRef<ReturnType<typeof useAgentSidebar> | null>(null);

    useImperativeHandle(
      ref,
      () => ({
        appendToComposer(markup: string) {
          if (!markup.trim()) return;
          setView("tasks");
          setInputValue((current) => appendMentionMarkup(current, markup));
        },
        prepareSceneDraft(request: SceneDraftRequest) {
          prepareSceneDraftActionRef.current(request);
        },
      }),
      [],
    );

    useEffect(() => {
      if (selectedModelId) {
        storeModelId(selectedModelId);
      }
    }, [selectedModelId]);

    useEffect(() => {
      const selectedAgent = primaryAgents.find((agent) => agent.key === selectedAgentKey);
      if (selectedAgentKey && !selectedAgent?.metadata.workflow_only) {
        storeAgentKey(selectedAgentKey);
      }
    }, [primaryAgents, selectedAgentKey]);

    useEffect(() => {
      setReasoningEffort(
        constrainReasoningEffort(
          getStoredReasoningEffort(
            effectiveModelId,
            Boolean(currentModel?.reasoningEffortLevels?.length),
          ),
          currentModel?.reasoningEffortLevels,
        ),
      );
    }, [currentModel?.reasoningEffortLevels, effectiveModelId]);

    const newTaskFolderRef = useRef<string | null>(null);
    const handleAgentTaskTitleUpdated = useCallback(
      (taskId: string, title: string, updatedAt?: string) => {
        const folderId = newTaskFolderRef.current;
        if (folderId) {
          newTaskFolderRef.current = null;
          void moveProjectFolderItem(projectId, "discussion", taskId, folderId)
            .then(() => queryClient.invalidateQueries({ queryKey: ["tasks", projectId] }))
            .catch(() => toast.error(t("projectNavigation.moveFailed")));
        }
        setCurrentTaskId(taskId);
        setCurrentTaskTitle(title);
        queryClient.setQueriesData({ queryKey: ["tasks", projectId], exact: false }, (current) => {
          if (!current || typeof current !== "object" || !("items" in current)) return current;
          const response = current as { items: TaskListItem[]; total: number };
          return {
            ...response,
            items: response.items.map((task) =>
              task.id === taskId
                ? { ...task, title, updatedAt: updatedAt ?? task.updatedAt }
                : task,
            ),
          };
        });
        queryClient.setQueryData(["task", taskId], (current) => {
          if (!current || typeof current !== "object") return current;
          return {
            ...current,
            title,
            updatedAt: updatedAt ?? (current as { updatedAt?: string }).updatedAt,
          };
        });
      },
      [projectId, queryClient, t],
    );

    const handleAgentForkCreated = useCallback(
      async (response: AgentForkResponse) => {
        try {
          const fullTask = await fetchTask(response.task_id);
          setContextMode(fullTask.contextMode);
          const forkTask: TaskListItem = {
            id: fullTask.id,
            projectId: fullTask.projectId,
            folderId: fullTask.folderId,
            title: fullTask.title,
            contextMode: fullTask.contextMode,
            tokenInput: fullTask.tokenInput,
            tokenOutput: fullTask.tokenOutput,
            tokenCache: fullTask.tokenCache,
            cost: fullTask.cost,
            contextInputTokens: fullTask.contextInputTokens,
            isRunning: fullTask.isRunning,
            isFavorited: fullTask.isFavorited,
            createdAt: fullTask.createdAt,
            updatedAt: fullTask.updatedAt,
          };
          const agentMessages = buildAgentMessagesFromTaskMessages(
            fullTask.messages,
            forkTask,
            fullTask.createdAt,
          );
          if (!fullTask.agentSessionId) {
            toast.error(t("assistant.forkMissingSessionId"));
            return;
          }
          const sessionId = fullTask.agentSessionId;
          agentSidebarRef.current?.loadSession(sessionId, agentMessages, {
            reconnect: false,
            isRemoteRunning: false,
          });
          setView("tasks");
          setIsLoadingTask(false);
          setCurrentTaskId(fullTask.id);
          setCurrentTaskTitle(fullTask.title);
          setSessionTotalUsage({
            sessionId,
            taskId: fullTask.id,
            tokenInput: fullTask.tokenInput,
            tokenOutput: fullTask.tokenOutput,
            tokenCache: fullTask.tokenCache,
            cost: fullTask.cost,
          });
          setConversationUsageBySession((current) => ({
            ...current,
            [sessionId]: buildTaskConversationUsage(
              fullTask,
              currentModel?.contextWindow ?? DEFAULT_CONTEXT_LENGTH,
            ),
          }));
          queryClient.invalidateQueries({ queryKey: ["tasks", projectId], exact: false });
        } catch (error) {
          console.error("Failed to load fork task:", error);
          toast.error(t("assistant.forkLoadFailed"));
        }
      },
      [currentModel, projectId, queryClient, t],
    );

    const handleToggleToolApprovalBypass = useCallback(() => {
      if (isTogglingToolApprovalBypass) return;
      const nextEnabled = !isToolApprovalBypassEnabled;
      toggleToolApprovalBypass(nextEnabled);
    }, [isToolApprovalBypassEnabled, isTogglingToolApprovalBypass, toggleToolApprovalBypass]);

    const handleAgentSessionCreated = useCallback(
      (response: AgentSessionCreateResponse) => {
        setCurrentTaskId(response.task_id);
        setCurrentTaskTitle(response.task_title);
        setContextMode(response.context_mode);
        setSessionTotalUsage(createSessionTotalUsageState(response.session_id, response.task_id));
        setConversationUsageBySession((current) => ({
          ...current,
          [response.session_id]: createTokenUsageState(
            currentModel?.contextWindow ?? DEFAULT_CONTEXT_LENGTH,
          ),
        }));
      },
      [currentModel?.contextWindow],
    );

    const handleConversationTokenUsage = useCallback(
      (sessionId: string, usage: TokenUsageState) => {
        setConversationUsageBySession((current) => ({
          ...current,
          [sessionId]: usage,
        }));
      },
      [],
    );

    const handleTaskUsageSnapshot = useCallback(
      (payload: TaskUsagePayload) =>
        setSessionTotalUsage((current) => applyTaskUsageSnapshot(current, payload)),
      [],
    );

    const handleTaskUsageDelta = useCallback(
      (payload: TaskUsagePayload) =>
        setSessionTotalUsage((current) => applyTaskUsageDelta(current, payload)),
      [],
    );

    const currentConversation = useMemo(
      () => getCurrentConversationDescriptor(conversationState),
      [conversationState],
    );
    const currentSubagentSnapshot = useMemo(
      () => getCurrentSubagentSnapshot(conversationState),
      [conversationState],
    );
    const isViewingSubagent = currentConversation?.kind === "subagent";
    const projectedSubagentSpecialPanels = useMemo(() => {
      if (isViewingSubagent) return [];
      const approvalMessages = activeSubagents.reduce<AgentMessage[]>((result, subagent) => {
        const message = createPendingApprovalMessage(subagent.pendingApproval);
        if (message) result.push(message);
        return result;
      }, []);
      return getAgentSpecialPanels(approvalMessages);
    }, [activeSubagents, isViewingSubagent]);

    const agentSidebar = useAgentSidebar({
      projectId,
      scrollToBottomKey: currentTaskId,
      modelId: effectiveModelId,
      reasoningEffort: constrainReasoningEffort(
        reasoningEffort,
        currentModel?.reasoningEffortLevels,
      ),
      deliveryMode,
      agentKey: effectiveAgentKey,
      contextMode,
      inputValue,
      attachments: pendingAttachments,
      onClearInput: () => setInputValue(""),
      onClearAttachments: () => {
        pendingAttachments.forEach((attachment) => {
          if (attachment.file) URL.revokeObjectURL(attachment.previewUrl);
        });
        setPendingAttachments([]);
      },
      onRestoreAttachments: (attachments) => {
        setPendingAttachments((current) => {
          current.forEach((attachment) => {
            if (attachment.file) URL.revokeObjectURL(attachment.previewUrl);
          });
          return createRestoredPendingAgentAttachments(attachments);
        });
      },
      onAppendRestoredAttachments: (attachments) => {
        setPendingAttachments((current) => [
          ...current,
          ...createRestoredPendingAgentAttachments(attachments).filter(
            (attachment) => !current.some((item) => item.id === attachment.id),
          ),
        ]);
      },
      onAppendRestoredInput: (content) =>
        setInputValue((current) => (current.trim() ? `${current}\n\n${content}` : content)),
      onSetInputValue: (value) => setInputValue(value),
      onOpenMentionChapter,
      sceneDraftTarget,
      onApplySceneDraft,
      onTokenUsage: handleConversationTokenUsage,
      onTaskUsageSnapshot: handleTaskUsageSnapshot,
      onTaskUsageDelta: handleTaskUsageDelta,
      onTaskTitleUpdated: handleAgentTaskTitleUpdated,
      onForkCreated: handleAgentForkCreated,
      onSessionCreated: handleAgentSessionCreated,
      onAgentConfirmed: (confirmedAgentKey) => {
        setSelectedAgentKey(confirmedAgentKey);
        const confirmedAgent = primaryAgents.find((agent) => agent.key === confirmedAgentKey);
        if (!confirmedAgent?.metadata.workflow_only) {
          storeAgentKey(confirmedAgentKey);
        }
      },
      projectedSpecialPanels: projectedSubagentSpecialPanels,
      onAtBottomChange: setIsMessagesAtBottom,
      scrollToBottomFnRef,
    });
    useEffect(() => {
      agentSidebarRef.current = agentSidebar;
    }, [agentSidebar]);
    const agentSidebarSessionId = agentSidebar.sessionId;
    const reconnectAgentTransport = agentSidebar.reconnectTransport;
    const parentConversationSessionId =
      agentSidebarSessionId ||
      (currentConversation?.kind === "parent"
        ? currentConversation.sessionId
        : currentConversation?.parentSessionId) ||
      "";
    const subagentSession = useSubagentSession(
      currentConversation?.kind === "subagent" ? currentConversation.childRunId : null,
      currentConversation?.kind === "subagent" ? currentConversation.childThreadId : null,
      handleConversationTokenUsage,
    );

    const currentConversationSessionId =
      currentConversation?.kind === "subagent"
        ? currentConversation.childThreadId
        : agentSidebarSessionId ||
          (currentConversation?.kind === "parent" ? currentConversation.sessionId : "") ||
          "";
    const currentConversationUsage = useMemo(
      () =>
        selectConversationUsage({
          usageBySession: conversationUsageBySession,
          sessionId: currentConversationSessionId,
          isSubagent: isViewingSubagent,
          subagentUsage: subagentSession.tokenUsage,
          contextLength: currentModel?.contextWindow ?? DEFAULT_CONTEXT_LENGTH,
        }),
      [
        conversationUsageBySession,
        currentConversationSessionId,
        currentModel?.contextWindow,
        isViewingSubagent,
        subagentSession.tokenUsage,
      ],
    );

    useEffect(() => {
      if (!onStateChange) return;
      onStateChange({
        agentStatus: isViewingSubagent ? subagentSession.status : agentSidebar.status,
        isAgentRunning: isViewingSubagent ? subagentSession.isRunning : agentSidebar.isRunning,
        conversationDescriptor: currentConversation,
        activeSubagents,
      });
    }, [
      activeSubagents,
      isViewingSubagent,
      agentSidebar.isRunning,
      agentSidebar.status,
      currentConversation,
      onStateChange,
      subagentSession.isRunning,
      subagentSession.status,
    ]);

    useEffect(() => {
      let cancelled = false;
      queueMicrotask(() => {
        if (cancelled) return;
        setInputValue("");
        setView("tasks");
        setIsLoadingTask(false);
        setCurrentTaskId(null);
        setCurrentTaskTitle("");
        setConversationState(createConversationStackState(""));
        setActiveSubagents([]);
        setSessionTotalUsage(createSessionTotalUsageState());
        setConversationUsageBySession({});
      });
      return () => {
        cancelled = true;
      };
    }, [projectId]);

    useEffect(() => {
      if (!agentSidebarSessionId) return undefined;
      let cancelled = false;
      const sessionId = agentSidebarSessionId;
      queueMicrotask(() => {
        if (cancelled) return;
        setConversationState((current) => {
          const synced = syncParentConversationState(current, sessionId);
          const parentEntry = synced.entries[0];
          if (!parentEntry || parentEntry.kind !== "parent") return synced;
          const nextTaskId = currentTaskId ?? parentEntry.taskId ?? null;
          const nextTaskTitle = currentTaskTitle || parentEntry.taskTitle || null;
          if (parentEntry.taskId === nextTaskId && parentEntry.taskTitle === nextTaskTitle) {
            return synced;
          }
          return {
            entries: [
              {
                ...parentEntry,
                taskId: nextTaskId,
                taskTitle: nextTaskTitle,
              },
              ...synced.entries.slice(1),
            ],
          };
        });
      });
      return () => {
        cancelled = true;
      };
    }, [agentSidebarSessionId, currentTaskId, currentTaskTitle]);

    useEffect(() => {
      if (!agentSidebarSessionId) return;
      void reconnectAgentTransport();
    }, [agentSidebarSessionId, reconnectAgentTransport]);

    useEffect(() => {
      if (!parentConversationSessionId) return undefined;

      const cleanup = subscribeSubagentStatusEvents(
        parentConversationSessionId,
        (event) => {
          setActiveSubagents((current) => upsertActiveSubagent(current, event));
          setConversationState((current) => {
            let changed = false;
            const nextEntries = current.entries.map((entry) => {
              if (entry.kind !== "subagent" || entry.childRunId !== event.childRunId) return entry;
              changed = true;
              return {
                ...entry,
                subagent: event,
              };
            });
            return changed ? { entries: nextEntries } : current;
          });
        },
        (error) => {
          console.warn("Subagent status stream disconnected", error);
        },
      );

      void joinSubagentStatusStream(parentConversationSessionId).catch((error) => {
        console.warn("Failed to join subagent status stream", error);
      });

      return () => {
        cleanup();
      };
    }, [parentConversationSessionId]);

    useAssistantTaskEvents(projectId, currentTaskId, setCurrentTaskTitle);

    const loadTaskById = useCallback(
      async (
        taskId: string,
        options: {
          initialTask?: TaskListItem;
          showSuccessToast?: boolean;
        } = {},
      ): Promise<boolean> => {
        newTaskFolderRef.current = null;
        setView("tasks");
        setIsLoadingTask(true);
        setActiveSubagents([]);

        try {
          const bundle = await loadAgentTaskBundle(taskId, {
            fetchTask,
            fetchAgentSessionState,
            fetchActiveSubagents,
          });
          const fullTask = bundle.task;
          setContextMode(fullTask.contextMode);

          if (!fullTask.agentSessionId) {
            toast.error(t("writing.aiSidebar.agentSessionNotFound"));
            setIsLoadingTask(false);
            return false;
          }
          const sessionId = fullTask.agentSessionId;

          const taskSnapshot = options.initialTask ?? {
            id: fullTask.id,
            projectId: fullTask.projectId,
            folderId: fullTask.folderId,
            title: fullTask.title,
            contextMode: fullTask.contextMode,
            tokenInput: fullTask.tokenInput,
            tokenOutput: fullTask.tokenOutput,
            tokenCache: fullTask.tokenCache,
            cost: fullTask.cost,
            contextInputTokens: fullTask.contextInputTokens,
            isRunning: fullTask.isRunning,
            isFavorited: fullTask.isFavorited,
            createdAt: fullTask.createdAt,
            updatedAt: fullTask.updatedAt,
          };

          const agentMessages = buildAgentMessagesFromTaskMessages(
            fullTask.messages,
            taskSnapshot,
            fullTask.createdAt,
          );

          const isRemoteRunning = bundle.sessionState?.isRunning ?? false;

          const restoredAgentKey =
            typeof bundle.sessionState?.state.agent_key === "string"
              ? bundle.sessionState.state.agent_key
              : undefined;
          if (restoredAgentKey && primaryAgents.some((agent) => agent.key === restoredAgentKey)) {
            setSelectedAgentKey(restoredAgentKey);
          }

          const restoredModelConfig = bundle.sessionState?.state.model_config;
          const restoredModelRecordId =
            restoredModelConfig &&
            typeof restoredModelConfig === "object" &&
            !Array.isArray(restoredModelConfig) &&
            typeof (restoredModelConfig as Record<string, unknown>).model_record_id === "string"
              ? ((restoredModelConfig as Record<string, unknown>).model_record_id as string)
              : undefined;
          const restoredModelId =
            restoredModelRecordId &&
            llmModelOptions.some((model) => getModelValue(model) === restoredModelRecordId)
              ? restoredModelRecordId
              : undefined;
          const restoredModel = restoredModelId
            ? llmModelOptions.find((model) => getModelValue(model) === restoredModelId)
            : undefined;
          if (restoredModelId) {
            setSelectedModelId(restoredModelId);
          }

          const restoredReasoningEffort =
            restoredModelConfig &&
            typeof restoredModelConfig === "object" &&
            !Array.isArray(restoredModelConfig) &&
            isReasoningEffort(
              (restoredModelConfig as Record<string, unknown>).reasoning_effort ?? "off",
            )
              ? (((restoredModelConfig as Record<string, unknown>).reasoning_effort as
                  | ReasoningEffort
                  | undefined) ?? "off")
              : undefined;
          if (restoredReasoningEffort) {
            const normalizedReasoningEffort = constrainReasoningEffort(
              restoredReasoningEffort,
              restoredModel?.reasoningEffortLevels,
            );
            if (restoredModelId) {
              storeReasoningEffort(restoredModelId, normalizedReasoningEffort);
            }
            setReasoningEffort(normalizedReasoningEffort);
          }

          agentSidebar.loadSession(sessionId, agentMessages, {
            reconnect: true,
            isRemoteRunning,
            pendingInterrupts: bundle.sessionState?.interrupts,
            primaryAgentKey: restoredAgentKey,
            modelId: restoredModelId,
          });
          setActiveSubagents(bundle.activeSubagentRows);
          setCurrentTaskId(fullTask.id);
          setCurrentTaskTitle(fullTask.title);
          setConversationState((current) => {
            const synced = syncParentConversationState(current, sessionId);
            const parentEntry = synced.entries[0];
            if (!parentEntry || parentEntry.kind !== "parent") return synced;
            return {
              entries: [
                {
                  ...parentEntry,
                  taskId: fullTask.id,
                  taskTitle: fullTask.title,
                },
                ...synced.entries.slice(1),
              ],
            };
          });
          setSessionTotalUsage({
            sessionId,
            taskId: fullTask.id,
            tokenInput: fullTask.tokenInput,
            tokenOutput: fullTask.tokenOutput,
            tokenCache: fullTask.tokenCache,
            cost: fullTask.cost,
          });
          setConversationUsageBySession((current) => ({
            ...current,
            [sessionId]: buildTaskConversationUsage(
              fullTask,
              currentModel?.contextWindow ?? DEFAULT_CONTEXT_LENGTH,
            ),
          }));

          if (options.showSuccessToast !== false) {
            toast.success(t("writing.aiSidebar.agentTaskLoaded"));
          }
          setIsLoadingTask(false);
          return true;
        } catch {
          setIsLoadingTask(false);
          toast.error(t("writing.aiSidebar.taskLoadFailed"));
          return false;
        }
      },
      [agentSidebar, currentModel?.contextWindow, llmModelOptions, primaryAgents, t],
    );

    const loadTask = useCallback(
      async (task: TaskListItem) => {
        void loadTaskById(task.id, {
          initialTask: task,
        });
      },
      [loadTaskById],
    );

    const handleToggleFavorite = useCallback(
      (taskId: string, isFavorited: boolean) => {
        updateTaskMutation.mutate({
          taskId,
          data: { is_favorited: isFavorited },
        });
      },
      [updateTaskMutation],
    );

    const handleRenameTask = useCallback(
      async (taskId: string, title: string) => {
        await updateTaskMutation.mutateAsync({
          taskId,
          data: { title },
        });
      },
      [updateTaskMutation],
    );

    const backToTaskList = useCallback(() => {
      newTaskFolderRef.current = null;
      setSessionTotalUsage(createSessionTotalUsageState());
      setConversationUsageBySession({});

      agentSidebar.resetSession();

      setConversationState(createConversationStackState(""));
      setActiveSubagents([]);
      setView("tasks");
      setIsLoadingTask(false);
      setCurrentTaskId(null);
      setCurrentTaskTitle("");
      setContextMode("local");
      setSceneDraftTarget(null);
      void refetchRecentTasks();
    }, [agentSidebar, refetchRecentTasks]);

    const prepareSceneDraft = useCallback(
      (request: SceneDraftRequest) => {
        if (agentSidebar.isRunning || agentSidebar.pendingMessage) {
          toast.error(t("writing.sceneDraft.busy"));
          return;
        }
        backToTaskList();
        setSceneDraftTarget(request);
        setContextMode(request.contextMode);
        setSelectedAgentKey("draft");
        setInputValue(request.prompt);
        setView("tasks");
      },
      [agentSidebar.isRunning, agentSidebar.pendingMessage, backToTaskList, t],
    );

    useEffect(() => {
      prepareSceneDraftActionRef.current = prepareSceneDraft;
    }, [prepareSceneDraft]);

    const openAllTasks = useCallback(() => {
      queryClient.invalidateQueries({ queryKey: ["tasks", projectId], exact: false });
      setView("allTasks");
    }, [projectId, queryClient]);

    const performSend = useCallback(() => {
      const hasCurrentTask = Boolean(agentSidebar.sessionId);

      if (!hasCurrentTask && inputValue.trim()) {
        const title = inputValue.trim();
        setCurrentTaskTitle(title.length > 50 ? `${title.slice(0, 50)}...` : title);
      }

      agentSidebar.onSend();
    }, [inputValue, agentSidebar]);

    const {
      summaryWarningOpen,
      handleSend,
      handleConfirmSummaryWarning,
      handleSummaryWarningOpenChange,
    } = useSummarySendGuard(
      projectId,
      Boolean(inputValue.trim()) || pendingAttachments.length > 0,
      performSend,
    );

    const handleAbort = useCallback(() => {
      agentSidebar.onAbort();
    }, [agentSidebar]);

    const canCompactAgentSession =
      Boolean(agentSidebar.sessionId) &&
      !isViewingSubagent &&
      !isLoadingTask &&
      !agentSidebar.isRunning &&
      !agentSidebar.isCompacting &&
      (agentSidebar.status === "idle" ||
        agentSidebar.status === "completed" ||
        agentSidebar.status === "error");
    const compactionTooltip = agentSidebar.isCompacting
      ? t("assistant.compactionInProgressTooltip")
      : isLoadingTask
        ? t("assistant.compactionLoadingSession")
        : isViewingSubagent
          ? t("assistant.compactionSubagentDisabled")
          : agentSidebar.isRunning
            ? t("assistant.compactionRunningDisabled")
            : agentSidebar.status === "waiting_answer" || agentSidebar.status === "waiting_approval"
              ? t("assistant.compactionPendingActionRequired")
              : agentSidebar.sessionId
                ? t("assistant.compactionAvailable")
                : t("assistant.compactionNoSession");
    const handleCompactSession = useCallback(() => {
      if (!canCompactAgentSession) return;
      void agentSidebar.compactSession();
    }, [agentSidebar, canCompactAgentSession]);

    const handleModelChange = useCallback((nextModelId: string) => {
      setSelectedModelId(nextModelId);
      storeModelId(nextModelId);
    }, []);

    const handleReasoningEffortChange = useCallback(
      (nextReasoningEffort: ReasoningEffort) => {
        if (!effectiveModelId) return;
        setReasoningEffort(nextReasoningEffort);
        storeReasoningEffort(effectiveModelId, nextReasoningEffort);
      },
      [effectiveModelId],
    );

    const hasActiveSession = Boolean(parentConversationSessionId);
    const handleAgentChange = useCallback(
      (nextAgentKey: string) => {
        if (nextAgentKey === effectiveAgentKey) return;
        if (agentSidebar.isRunning || agentSidebar.pendingMessage) {
          toast.error(t("assistant.agentSwitchWhileRunning"));
          return;
        }
        if (
          hasActiveSession &&
          contextMode === "global" &&
          !primaryAgents.find((agent) => agent.key === nextAgentKey)?.metadata
            .supports_global_context
        ) {
          toast.error(t("assistant.globalDiscussionAgentLocked"));
          return;
        }
        if (
          !hasActiveSession &&
          !primaryAgents.find((agent) => agent.key === nextAgentKey)?.metadata
            .supports_global_context
        )
          setContextMode("local");
        setSelectedAgentKey(nextAgentKey);
        storeAgentKey(nextAgentKey);
        if (hasActiveSession) {
          const agentName = primaryAgents.find((agent) => agent.key === nextAgentKey)?.display_name;
          toast.success(t("assistant.agentSwitchNextTurn", { agent: agentName || nextAgentKey }));
        }
      },
      [
        agentSidebar.isRunning,
        agentSidebar.pendingMessage,
        contextMode,
        effectiveAgentKey,
        hasActiveSession,
        primaryAgents,
        t,
      ],
    );

    const supportsGlobalScope = Boolean(
      primaryAgents.find((agent) => agent.key === effectiveAgentKey)?.metadata
        .supports_global_context,
    );
    const handleStartDiscussion = useCallback(
      (nextContextMode: "global" | "local") => {
        backToTaskList();
        setContextMode(nextContextMode);
        setSelectedAgentKey("discuss");
        storeAgentKey("discuss");
      },
      [backToTaskList],
    );
    const scopeChangeDisabled =
      isViewingSubagent ||
      isLoadingTask ||
      isUpdatingScope ||
      agentSidebar.isRunning ||
      agentSidebar.isCompacting ||
      Boolean(agentSidebar.pendingMessage) ||
      agentSidebar.status === "waiting_answer" ||
      agentSidebar.status === "waiting_approval";
    const handleKnowledgeScopeChange = useCallback(
      async (nextContextMode: "global" | "local") => {
        if (scopeChangeDisabled || nextContextMode === contextMode) return;
        if (hasActiveSession && contextMode === "global") return;
        if (nextContextMode === "global" && !supportsGlobalScope) return;
        setIsUpdatingScope(true);
        try {
          if (parentConversationSessionId) {
            await updateAgentKnowledgeScope(
              parentConversationSessionId,
              nextContextMode,
              effectiveAgentKey,
            );
          }
          setContextMode(nextContextMode);
        } catch (error) {
          toast.error(
            error instanceof Error ? error.message : t("assistant.knowledgeScopeUpdateFailed"),
          );
        } finally {
          setIsUpdatingScope(false);
        }
      },
      [
        scopeChangeDisabled,
        contextMode,
        hasActiveSession,
        supportsGlobalScope,
        parentConversationSessionId,
        effectiveAgentKey,
        t,
      ],
    );

    useEffect(() => {
      if (!preferredAgentKey) {
        handledPreferredAgentRef.current = null;
        return;
      }

      const requestKey = `${projectId}:${preferredAgentKey}`;
      if (handledPreferredAgentRef.current === requestKey) return;
      if (!primaryAgents.some((agent) => agent.key === preferredAgentKey)) return;

      handledPreferredAgentRef.current = requestKey;
      if (preferredAgentKey === "discuss") {
        if (hasActiveSession && effectiveAgentKey === "discuss") return;
        handleStartDiscussion("local");
        return;
      }

      handleAgentChange(preferredAgentKey);
    }, [
      effectiveAgentKey,
      handleAgentChange,
      handleStartDiscussion,
      hasActiveSession,
      preferredAgentKey,
      primaryAgents,
      projectId,
    ]);

    useEffect(() => {
      const nextMarkup = initialComposerMarkup?.trim() || null;
      const requestKey = `${projectId}:${replaceComposerWithInitialMarkup ? "replace" : "merge"}:${nextMarkup ?? ""}`;
      if (handledInitialComposerMarkupRef.current === requestKey) return;
      handledInitialComposerMarkupRef.current = requestKey;
      const previousMarkup = automaticComposerMarkupRef.current;
      automaticComposerMarkupRef.current = nextMarkup;

      let cancelled = false;
      queueMicrotask(() => {
        if (cancelled) return;
        setInputValue((current) =>
          replaceComposerWithInitialMarkup
            ? (nextMarkup ?? "")
            : replaceAutomaticMentionMarkup(current, previousMarkup, nextMarkup),
        );
      });
      return () => {
        cancelled = true;
      };
    }, [initialComposerMarkup, projectId, replaceComposerWithInitialMarkup]);

    const agentSelectorOptions = useMemo(
      () =>
        primaryAgents
          .filter(
            (definition) =>
              !definition.metadata.workflow_only || definition.key === effectiveAgentKey,
          )
          .filter(
            (definition) =>
              !hasActiveSession ||
              contextMode !== "global" ||
              definition.metadata.supports_global_context,
          )
          .map((d) => ({
            value: d.key,
            label: d.display_name || d.key,
            description: getAgentDisplayDescription(d.key, d.description || "") || undefined,
            labelColor: getAgentIconColor(d.color),
            prefix: (
              <AgentBrandIcon
                color={d.color}
                icon={d.icon}
                size={14}
              />
            ),
          })),
      [effectiveAgentKey, primaryAgents, hasActiveSession, contextMode],
    );

    const handleGoToSettings = useCallback(() => {
      openSettings({ category: "models", modelTab: "llm" });
    }, [openSettings]);

    const handleOpenSubagent = useCallback(
      (subagent: ActiveSubagentState) => {
        if (!parentConversationSessionId) return;
        setConversationState((current) =>
          openSubagentConversation(current, parentConversationSessionId, subagent),
        );
      },
      [parentConversationSessionId],
    );

    const handleReturnToPrimary = useCallback(async () => {
      const parentEntry = conversationState.entries[0];
      if (
        !agentSidebar.sessionId &&
        parentEntry?.kind === "parent" &&
        typeof parentEntry.taskId === "string" &&
        parentEntry.taskId
      ) {
        const restored = await loadTaskById(parentEntry.taskId, {
          showSuccessToast: false,
        });
        if (!restored) return;
      }
      setConversationState((current) => returnToPrimaryConversation(current));
    }, [agentSidebar.sessionId, conversationState.entries, loadTaskById]);

    const recentTasks = tasksData?.items ?? [];
    const hasRecentTasks = recentTasks.length > 0;

    const hasActiveTask = hasActiveSession;

    const shouldShowMobileToolbar = isMobileOverlay && view !== "allTasks" && !hasActiveTask;

    const isSendingMessage = agentSidebar.isRunning;
    const shouldShowSubagentConversation = isViewingSubagent;
    const shouldShowParentSubagentStrip =
      view !== "allTasks" &&
      hasActiveTask &&
      !isLoadingTask &&
      !isViewingSubagent &&
      activeSubagents.length > 0;
    const subagentSpecialPanels = useMemo(
      () => getAgentSpecialPanels(subagentSession.messages),
      [subagentSession.messages],
    );
    const subagentHeaderLabel = formatSubagentDisplayLabel(
      subagentSession.session?.agentKey ?? currentSubagentSnapshot?.agentKey,
      subagentSession.session?.agentNumber ?? currentSubagentSnapshot?.agentNumber,
    );
    const subagentStatusValue =
      subagentSession.session?.status ?? currentSubagentSnapshot?.status ?? "";
    const subagentStatusLabel = getSubagentStatusLabel(subagentStatusValue, t);
    const subagentReadOnlyMessage = (
      <span className="ai-sidebar-readonly-message">
        {!subagentStatusValue ? <span>{t("writing.aiSidebar.subagentInactive")} · </span> : null}
        <span>{t("writing.aiSidebar.subagentReadOnly")}</span>
        <button
          type="button"
          className="ai-sidebar-readonly-return-link"
          onClick={() => {
            void handleReturnToPrimary();
          }}
          aria-label={t("writing.aiSidebar.returnToPrimary")}
        >
          <span className="ai-sidebar-readonly-return-label">
            {t("writing.aiSidebar.returnToPrimary")}
          </span>
          <SquareArrowOutUpRight
            size={12}
            strokeWidth={2}
            className="ai-sidebar-readonly-return-icon"
            aria-hidden="true"
          />
        </button>
      </span>
    );
    const projectActions =
      primaryAgents.length > 0 || (!discussionWorkspace && pendingCount > 0) ? (
        <AssistantProjectActions
          projectId={projectId}
          hasAgents={primaryAgents.length > 0}
          discussionWorkspace={discussionWorkspace}
          pendingCount={pendingCount}
          contextMode={contextMode}
          scopeChangeDisabled={scopeChangeDisabled}
          supportsGlobalScope={supportsGlobalScope}
          hasActiveSession={hasActiveSession}
          onKnowledgeScopeChange={handleKnowledgeScopeChange}
        />
      ) : null;
    const headerBackLabel = isViewingSubagent
      ? t("writing.aiSidebar.returnToPrimary")
      : t("common.back");
    const handleHeaderBack = isViewingSubagent ? handleReturnToPrimary : backToTaskList;

    // Keep the layout sequence here: navigation, header, message viewport, floating controls, composer.
    return (
      <Flex className="ai-sidebar-layout">
        {discussionWorkspace && (
          <ProjectNavShell>
            <AllTasksPage
              projectId={projectId}
              onBack={() => undefined}
              onTaskClick={loadTask}
              activeTaskId={currentTaskId}
              showBack={false}
              title={t("assistant.discussionHistory")}
              onNew={(folderId) => {
                backToTaskList();
                newTaskFolderRef.current = folderId ?? null;
              }}
              newLabel={t("assistant.newDiscussion")}
              searchPlaceholder={t("assistant.searchDiscussions")}
              emptyLabel={t("assistant.noDiscussions")}
            />
          </ProjectNavShell>
        )}
        <Flex
          direction="column"
          height="100%"
          className="ai-sidebar-shell"
          data-discussion-workspace={discussionWorkspace}
        >
          {shouldShowMobileToolbar && (
            <Flex
              align="center"
              gap="2"
              className="ai-sidebar-mobile-toolbar"
            >
              <IconButton
                variant="ghost"
                size="2"
                onClick={onClose}
                aria-label={t("common.close")}
              >
                <ArrowLeft size={18} />
              </IconButton>
              <Text
                size="2"
                weight="medium"
              >
                {t("assistant.mobileTitle")}
              </Text>
            </Flex>
          )}

          {view !== "allTasks" && discussionWorkspace ? projectActions : null}

          {view !== "allTasks" && hasActiveTask && (
            <AssistantSessionHeader
              discussionWorkspace={discussionWorkspace}
              isViewingSubagent={isViewingSubagent}
              subagentHeaderLabel={subagentHeaderLabel}
              subagentStatusLabel={subagentStatusLabel}
              currentTaskTitle={currentTaskTitle}
              supportsGlobalScope={supportsGlobalScope}
              contextMode={contextMode}
              headerBackLabel={headerBackLabel}
              onBack={handleHeaderBack}
              onCompact={handleCompactSession}
              onHistory={openAllTasks}
              onNewTask={backToTaskList}
              canCompactAgentSession={canCompactAgentSession}
              compactionTooltip={compactionTooltip}
              isCompacting={agentSidebar.isCompacting}
              sessionTotalDisplay={sessionTotalUsage}
              currentConversationUsage={currentConversationUsage}
            />
          )}

          {shouldShowParentSubagentStrip ? (
            <Box className="ai-sidebar-subagent-strip-wrap">
              <ActiveSubagentList
                items={activeSubagents}
                title={t("writing.aiSidebar.activeSubagents")}
                onOpen={handleOpenSubagent}
              />
            </Box>
          ) : null}

          {view === "allTasks" && !discussionWorkspace ? (
            <AllTasksPage
              projectId={projectId}
              onBack={() => {
                setView("tasks");
                void refetchRecentTasks();
              }}
              onTaskClick={loadTask}
            />
          ) : (
            <>
              <Box className="ai-sidebar-messages ai-sidebar-messages--frame">
                {agentSidebar.isRollbacking ? (
                  <Flex
                    className="ai-sidebar-rollback-overlay"
                    direction="column"
                    align="center"
                    justify="center"
                    role="status"
                    aria-live="polite"
                  >
                    <Spinner size={18} />
                    <Text
                      size="2"
                      className="ai-sidebar-rollback-text"
                    >
                      {t("assistant.rollbacking")}
                    </Text>
                  </Flex>
                ) : null}
                {isLoadingTask ? (
                  <Flex
                    direction="column"
                    align="center"
                    justify="center"
                    className="ai-sidebar-loading-state"
                  >
                    <Spinner size={18} />
                    <Text
                      size="2"
                      color="gray"
                    >
                      {t("assistant.loadingTask")}
                    </Text>
                  </Flex>
                ) : shouldShowSubagentConversation ? (
                  <AgentMessages
                    messages={subagentSession.messages}
                    isRunning={subagentSession.isRunning}
                    isRollbacking={false}
                    status={subagentSession.status}
                    currentStage={subagentSession.currentStage}
                    scrollToBottomKey={
                      currentConversation?.kind === "subagent"
                        ? currentConversation.childRunId
                        : undefined
                    }
                    onRollback={async () => null}
                    onAbortRetry={subagentSession.cancelSession}
                    onAtBottomChange={setIsMessagesAtBottom}
                    scrollToBottomFnRef={scrollToBottomFnRef}
                  />
                ) : !hasActiveTask && discussionWorkspace ? (
                  <Flex
                    align="center"
                    justify="center"
                    height="100%"
                    px="5"
                  >
                    <Text
                      size="2"
                      color="gray"
                      align="center"
                    >
                      {t("assistant.discussionEmptyHint")}
                    </Text>
                  </Flex>
                ) : !hasActiveTask ? (
                  <RecentTasksCard
                    tasks={recentTasks}
                    hasRecentTasks={hasRecentTasks}
                    onTaskClick={loadTask}
                    onToggleFavorite={handleToggleFavorite}
                    onRenameTask={handleRenameTask}
                    onViewAll={openAllTasks}
                  />
                ) : (
                  agentSidebar.MessagesComponent
                )}
              </Box>

              <div
                className="ai-sidebar-scroll-to-bottom"
                data-visible={!isLoadingTask && hasActiveTask && !isMessagesAtBottom}
              >
                <IconButton
                  size="2"
                  variant="solid"
                  color="gray"
                  onClick={() => scrollToBottomFnRef.current?.()}
                  aria-label={t("assistant.scrollToBottom")}
                >
                  <ArrowDown size={16} />
                </IconButton>
              </div>

              {!isViewingSubagent && agentSidebar.sessionId ? (
                <SessionTaskList
                  key={agentSidebar.sessionId}
                  sessionId={agentSidebar.sessionId}
                  isRunning={isSendingMessage}
                />
              ) : null}
              <AgentInput
                header={!discussionWorkspace ? projectActions : undefined}
                specialPanels={
                  isViewingSubagent ? (
                    <AgentSpecialPanels
                      panels={subagentSpecialPanels}
                      embedded
                      onApproveTool={subagentSession.handleToolApproval}
                      readOnly
                    />
                  ) : (
                    agentSidebar.SpecialPanelsComponent
                  )
                }
                value={inputValue}
                automaticComposerMarkup={automaticComposerMarkupRef.current}
                restorePersistedDraft={!replaceComposerWithInitialMarkup}
                attachments={pendingAttachments}
                projectId={projectId}
                modelId={effectiveModelId}
                models={llmModelOptions}
                reasoningEffort={reasoningEffort}
                isSending={isSendingMessage}
                disabled={isViewingSubagent || isLoadingTask}
                pendingMessages={isViewingSubagent ? [] : agentSidebar.pendingMessages}
                deliveryMode={deliveryMode}
                onDeliveryModeChange={setDeliveryMode}
                isModelsLoading={isModelsLoading}
                modelsError={!!modelsError}
                onChange={setInputValue}
                onAttachmentsChange={setPendingAttachments}
                onUploadAttachments={async (files) => {
                  setPendingAttachments((current) => [
                    ...current,
                    ...files.map((file) => ({
                      id: crypto.randomUUID(),
                      file,
                      previewUrl: URL.createObjectURL(file),
                    })),
                  ]);
                }}
                onSend={isViewingSubagent ? () => undefined : handleSend}
                onAbort={isViewingSubagent ? () => undefined : handleAbort}
                onCancelPendingMessage={
                  isViewingSubagent ? undefined : agentSidebar.onCancelPendingMessage
                }
                onOpenMentionChapter={onOpenMentionChapter}
                onModelChange={handleModelChange}
                onReasoningEffortChange={handleReasoningEffortChange}
                agentKey={effectiveAgentKey}
                agentOptions={agentSelectorOptions}
                agentChangeDisabled={
                  isSendingMessage ||
                  Boolean(agentSidebar.pendingMessage) ||
                  isUpdatingScope ||
                  effectiveAgentKey === "draft"
                }
                onAgentChange={handleAgentChange}
                onGoToSettings={handleGoToSettings}
                agentStatus={isViewingSubagent ? subagentSession.status : agentSidebar.status}
                toolApprovalBypassEnabled={isToolApprovalBypassEnabled}
                toolApprovalBypassDisabled={!settings || isTogglingToolApprovalBypass}
                onToggleToolApprovalBypass={handleToggleToolApprovalBypass}
                forceSpecialPanels={!isViewingSubagent && projectedSubagentSpecialPanels.length > 0}
                readOnly={isViewingSubagent}
                readOnlyMessage={subagentReadOnlyMessage}
              />
              <ConfirmDialog
                open={summaryWarningOpen}
                onOpenChange={handleSummaryWarningOpenChange}
                onConfirm={handleConfirmSummaryWarning}
                title={t("assistant.summaryWarningTitle")}
                description={t("assistant.summaryWarningDescription")}
                confirmText={t("assistant.summaryWarningConfirm")}
                cancelText={t("common.cancel")}
                confirmColor="blue"
              />
            </>
          )}
        </Flex>
      </Flex>
    );
  },
);
