import type {
  ActiveSubagentState,
  AgentCancelPendingMessageResponse,
  AgentCancelResponse,
  AgentCompactionResponse,
  AgentForkResponse,
  AgentImageAttachment,
  AgentInterruptBatchResponse,
  AgentPendingMessage,
  AgentQuestionAnswerResponse,
  AgentRollbackResponse,
  AgentSendMessageRequest,
  AgentSendMessageResponse,
  AgentSessionCreateRequest,
  AgentSessionCreateResponse,
  AgentSessionStateResponse,
  ClarificationAnswerItem,
  ReasoningEffort,
  SubagentSessionPayload,
} from "@/lib/agent.types";
import { apiClient, resolveBackendUrl } from "@/lib/api-transport";
import {
  subscribeBackgroundEvents,
  subscribeBackgroundProjection,
  type BackgroundEvent,
  type BackgroundEventSubscription,
  type BackgroundProjectionSubscription,
  type BackgroundSnapshot,
} from "@/lib/background-socket";
import type { Task, TaskListItem, TaskListResponse, UpdateTaskRequest } from "@/lib/task.types";

export {
  subscribeBackgroundEvents,
  subscribeBackgroundProjection,
  type BackgroundEvent,
  type BackgroundEventSubscription,
  type BackgroundProjectionSubscription,
  type BackgroundSnapshot,
};

function normalizeUtcDateString(value: unknown): string {
  if (typeof value !== "string") return "";

  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  if (hasTimezone) return value;

  return `${value}Z`;
}

function transformTaskMessage(raw: Record<string, unknown>): Task["messages"][number] {
  return {
    id: raw.id as string,
    taskId: (raw.task_id ?? raw.taskId) as string | null | undefined,
    role: raw.role as "system" | "user" | "assistant" | "tool",
    agentId: (raw.agent_id ?? raw.agentId) as string | null | undefined,
    content: raw.content as string,
    toolCalls: (raw.tool_calls ?? raw.toolCalls) as Record<string, unknown>[] | undefined,
    toolCallId: (raw.tool_call_id ?? raw.toolCallId) as string | null | undefined,
    metadata: (raw.metadata as Record<string, unknown> | null | undefined) ?? undefined,
    messageType: (raw.message_type ?? raw.messageType) as string | null | undefined,
    messageStatus: (raw.message_status ?? raw.messageStatus) as string | null | undefined,
    displayChannel: (raw.display_channel ?? raw.displayChannel) as string | null | undefined,
    payload: (raw.payload as Record<string, unknown> | null | undefined) ?? undefined,
    correlationId: (raw.correlation_id ?? raw.correlationId) as string | null | undefined,
    createdAt: normalizeUtcDateString(raw.created_at ?? raw.createdAt),
    updatedAt: normalizeUtcDateString(raw.updated_at ?? raw.updatedAt),
  };
}

function transformTask(raw: Record<string, unknown>): Task {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    folderId: (raw.folder_id as string | null | undefined) ?? null,
    title: raw.title as string,
    contextMode: (raw.context_mode ?? "local") as "global" | "local",
    messages: ((raw.messages as Record<string, unknown>[] | undefined) ?? []).map(
      transformTaskMessage,
    ),
    tokenInput: Number(raw.token_input ?? raw.tokenInput ?? 0),
    tokenOutput: Number(raw.token_output ?? raw.tokenOutput ?? 0),
    tokenCache: Number(raw.token_cache ?? raw.tokenCache ?? 0),
    contextInputTokens: Number(raw.context_input_tokens ?? raw.contextInputTokens ?? 0),
    cost: Number(raw.cost ?? 0),
    isRunning: raw.is_running === true,
    currentRevisionId: raw.current_revision_id as string | null | undefined,
    currentMessageId: raw.current_message_id as string | null | undefined,
    agentSessionId: raw.agent_session_id as string | null | undefined,
    isFavorited: raw.is_favorited as boolean,
    createdAt: normalizeUtcDateString(raw.created_at),
    updatedAt: normalizeUtcDateString(raw.updated_at),
  };
}

function transformTaskListItem(raw: Record<string, unknown>): TaskListItem {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    folderId: (raw.folder_id as string | null | undefined) ?? null,
    title: raw.title as string,
    contextMode: (raw.context_mode ?? "local") as "global" | "local",
    tokenInput: Number(raw.token_input ?? raw.tokenInput ?? 0),
    tokenOutput: Number(raw.token_output ?? raw.tokenOutput ?? 0),
    tokenCache: Number(raw.token_cache ?? raw.tokenCache ?? 0),
    contextInputTokens: Number(raw.context_input_tokens ?? raw.contextInputTokens ?? 0),
    cost: Number(raw.cost ?? 0),
    isRunning: raw.is_running === true,
    isFavorited: raw.is_favorited as boolean,
    createdAt: normalizeUtcDateString(raw.created_at),
    updatedAt: normalizeUtcDateString(raw.updated_at),
  };
}

export async function fetchTask(taskId: string): Promise<Task> {
  const response = await apiClient.get(`/tasks/${taskId}`);
  return transformTask(response.data);
}

export async function fetchTasks(
  projectId: string,
  params?: {
    limit?: number;
    offset?: number;
    search?: string;
    favorited?: boolean;
  },
): Promise<TaskListResponse> {
  const response = await apiClient.get(`/projects/${projectId}/tasks`, {
    params: {
      limit: params?.limit,
      offset: params?.offset,
      search: params?.search,
      favorited: params?.favorited,
    },
  });
  return {
    items: (response.data.items as Record<string, unknown>[]).map(transformTaskListItem),
    total: response.data.total,
  };
}

export async function updateTask(taskId: string, data: UpdateTaskRequest): Promise<Task> {
  const response = await apiClient.patch(`/tasks/${taskId}`, {
    title: data.title,
    is_favorited: data.is_favorited,
  });
  return transformTask(response.data);
}

export async function deleteTask(taskId: string): Promise<void> {
  await apiClient.delete(`/tasks/${taskId}`);
}

export async function deleteAllTasks(
  projectId: string,
): Promise<{ deletedCount: number; skippedRunningCount: number }> {
  const response = await apiClient.delete(`/projects/${projectId}/tasks`);
  return {
    deletedCount: Number(response.data.deleted_count ?? 0),
    skippedRunningCount: Number(response.data.skipped_running_count ?? 0),
  };
}

export async function createAgentSession(
  data: AgentSessionCreateRequest,
): Promise<AgentSessionCreateResponse> {
  const response = await apiClient.post("/agent/sessions", data);
  return response.data;
}

export async function updateAgentKnowledgeScope(
  sessionId: string,
  contextMode: "global" | "local",
  agentKey: string,
): Promise<{ context_mode: "global" | "local" }> {
  const response = await apiClient.patch(`/agent/sessions/${sessionId}/knowledge-scope`, {
    context_mode: contextMode,
    agent_key: agentKey,
  });
  return response.data;
}

export async function fetchAgentSessionState(
  sessionId: string,
): Promise<AgentSessionStateResponse> {
  const response = await apiClient.get(`/agent/sessions/${sessionId}`);
  const data = response.data as Record<string, unknown>;
  return {
    sessionId: String(data.session_id ?? sessionId),
    state:
      data.state && typeof data.state === "object" && !Array.isArray(data.state)
        ? (data.state as Record<string, unknown>)
        : {},
    isRunning: data.is_running === true,
    interrupts: Array.isArray(data.interrupts)
      ? data.interrupts.filter((item): item is Record<string, unknown> =>
          Boolean(item && typeof item === "object" && !Array.isArray(item)),
        )
      : [],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function transformPendingAgentMessage(raw: unknown): AgentPendingMessage | null {
  if (!isRecord(raw)) return null;
  const messageId = String(raw.message_id ?? "");
  const content = String(raw.content ?? "");
  const createdAt = String(raw.created_at ?? "");
  if (!messageId || !content || !createdAt) return null;
  return {
    messageId,
    content,
    createdAt,
  };
}

function transformActiveSubagentState(raw: Record<string, unknown>): ActiveSubagentState {
  const metadata = raw.metadata;
  const metadataRecord = isRecord(metadata) ? metadata : null;
  const pendingApproval = isRecord(raw.pending_approval) ? raw.pending_approval : null;
  return {
    childRunId: String(raw.child_run_id ?? ""),
    childThreadId: String(raw.child_thread_id ?? ""),
    agentKey: raw.agent_key as ActiveSubagentState["agentKey"],
    agentNumber: String(raw.agent_number ?? metadataRecord?.agent_number ?? "") || undefined,
    status: raw.status as ActiveSubagentState["status"],
    queuedMessages: Number(raw.queued_messages ?? 0),
    isActive: raw.is_active === true,
    pendingApproval,
  };
}

function transformSubagentSessionPayload(raw: Record<string, unknown>): SubagentSessionPayload {
  const metadata = raw.metadata;
  const metadataRecord = isRecord(metadata) ? metadata : null;
  const pendingApproval = isRecord(raw.pending_approval) ? raw.pending_approval : null;
  return {
    childRunId: String(raw.child_run_id ?? ""),
    childThreadId: String(raw.child_thread_id ?? ""),
    parentSessionId: String(raw.parent_session_id ?? ""),
    agentKey: raw.agent_key as SubagentSessionPayload["agentKey"],
    agentNumber: String(raw.agent_number ?? metadataRecord?.agent_number ?? "") || undefined,
    status: raw.status as SubagentSessionPayload["status"],
    isActive: raw.is_active === true,
    isRunning: raw.is_running === true,
    tokenInput: Number(raw.token_input ?? 0),
    tokenOutput: Number(raw.token_output ?? 0),
    tokenCache: Number(raw.token_cache ?? 0),
    cost: Number(raw.cost ?? 0),
    contextInputTokens: Number(raw.context_input_tokens ?? 0),
    contextLength: Number(raw.context_length ?? 0),
    pendingApproval,
    messages: ((raw.messages as Record<string, unknown>[] | undefined) ?? []).map(
      transformTaskMessage,
    ),
  };
}

export async function fetchActiveSubagents(
  parentSessionId: string,
): Promise<ActiveSubagentState[]> {
  const response = await apiClient.get(`/agent/sessions/${parentSessionId}/subagents`);
  return ((response.data as Record<string, unknown>[] | undefined) ?? []).map(
    transformActiveSubagentState,
  );
}

export async function fetchSubagentSession(childRunId: string): Promise<SubagentSessionPayload> {
  const response = await apiClient.get(`/agent/subagents/${childRunId}`);
  return transformSubagentSessionPayload(response.data as Record<string, unknown>);
}

export async function cancelSubagentSession(
  parentSessionId: string,
  childRunId: string,
): Promise<AgentCancelResponse> {
  const response = await apiClient.post(
    `/agent/sessions/${parentSessionId}/subagents/${childRunId}/cancel`,
  );
  const data = response.data as Record<string, unknown>;
  return {
    success: data.success === true,
    session_id: String(data.session_id ?? childRunId),
    message: String(data.message ?? ""),
  };
}

export async function sendAgentMessage(
  sessionId: string,
  message: string,
  modelId?: string,
  reasoningEffort?: ReasoningEffort,
  agentKey?: string,
  attachments?: AgentImageAttachment[],
): Promise<AgentSendMessageResponse> {
  const request: AgentSendMessageRequest = {
    message,
    ...(modelId ? { model_id: modelId } : {}),
    ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
    ...(agentKey ? { agent_key: agentKey } : {}),
    ...(attachments?.length ? { attachments: attachments.map((attachment) => attachment.id) } : {}),
  };
  const response = await apiClient.post(`/agent/sessions/${sessionId}/message`, request);
  const data = response.data as Record<string, unknown>;
  return {
    success: data.success === true,
    session_id: String(data.session_id ?? sessionId),
    message: String(data.message ?? ""),
    agent_key: String(data.agent_key ?? ""),
    queued: data.queued === true,
    model_updated: data.model_updated === true,
    task_id: String(data.task_id ?? ""),
    task_title: String(data.task_title ?? ""),
    pending_message: transformPendingAgentMessage(data.pending_message),
  };
}

export async function uploadAgentImageAttachment(
  sessionId: string,
  image: File,
): Promise<AgentImageAttachment> {
  const formData = new FormData();
  formData.append("image", image);
  const response = await apiClient.post(`/agent/sessions/${sessionId}/attachments`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  const raw = response.data as Record<string, unknown>;
  return {
    id: String(raw.id ?? ""),
    sessionId: String(raw.session_id ?? sessionId),
    storageName: String(raw.storage_name ?? ""),
    fileName: String(raw.file_name ?? ""),
    mimeType: raw.mime_type as AgentImageAttachment["mimeType"],
    sizeBytes: Number(raw.size_bytes ?? 0),
    width: Number(raw.width ?? 0),
    height: Number(raw.height ?? 0),
    url: resolveBackendUrl(String(raw.url ?? "")) ?? "",
  };
}

export async function compactAgentSession(sessionId: string): Promise<AgentCompactionResponse> {
  const response = await apiClient.post(`/agent/sessions/${sessionId}/compaction`);
  const data = response.data as Record<string, unknown>;
  return {
    success: data.success === true,
    session_id: String(data.session_id ?? sessionId),
    compaction_id: String(data.compaction_id ?? ""),
    start_seq: Number(data.start_seq ?? 0),
    end_seq: Number(data.end_seq ?? 0),
    source_input_tokens: Number(data.source_input_tokens ?? 0),
    summary_tokens: Number(data.summary_tokens ?? 0),
  };
}

export async function submitAgentQuestionAnswer(
  sessionId: string,
  actionId: string,
  answer: ClarificationAnswerItem[],
  skipped = false,
): Promise<AgentQuestionAnswerResponse | void> {
  const response = await apiClient.post(`/agent/sessions/${sessionId}/question-answer`, {
    action_id: actionId,
    answer,
    skipped,
  });
  return response.data;
}

export async function rollbackAgentRevision(
  sessionId: string,
  revisionId: string,
): Promise<AgentRollbackResponse> {
  const response = await apiClient.post(`/agent/sessions/${sessionId}/rollback`, {
    revision_id: revisionId,
  });
  const data = response.data as Record<string, unknown>;
  return {
    success: data.success === true,
    session_id: String(data.session_id ?? sessionId),
    revision_id: typeof data.revision_id === "string" ? data.revision_id : null,
    affected_chapters: Array.isArray(data.affected_chapters)
      ? data.affected_chapters.filter((item): item is string => typeof item === "string")
      : [],
    affected_notes: Array.isArray(data.affected_notes)
      ? data.affected_notes.filter((item): item is string => typeof item === "string")
      : [],
    affected_note_categories: Array.isArray(data.affected_note_categories)
      ? data.affected_note_categories.filter((item): item is string => typeof item === "string")
      : [],
    affected_world_entries: Array.isArray(data.affected_world_entries)
      ? data.affected_world_entries.filter((item): item is string => typeof item === "string")
      : [],
    restored_message_content: String(data.restored_message_content ?? ""),
    restored_attachments: Array.isArray(data.restored_attachments)
      ? data.restored_attachments.flatMap((attachment) => {
          if (!isRecord(attachment)) return [];
          if (
            typeof attachment.id !== "string" ||
            typeof attachment.url !== "string" ||
            typeof attachment.mime_type !== "string"
          )
            return [];
          return [
            {
              id: attachment.id,
              sessionId: String(attachment.session_id ?? sessionId),
              storageName: String(attachment.storage_name ?? ""),
              fileName: String(attachment.file_name ?? ""),
              mimeType: attachment.mime_type as AgentImageAttachment["mimeType"],
              sizeBytes: Number(attachment.size_bytes ?? 0),
              width: Number(attachment.width ?? 0),
              height: Number(attachment.height ?? 0),
              url: resolveBackendUrl(attachment.url) ?? "",
            },
          ];
        })
      : [],
  };
}

export async function forkAgentSession(
  sessionId: string,
  sourceRevisionId: string,
  modelId: string,
  reasoningEffort?: ReasoningEffort,
): Promise<AgentForkResponse> {
  const response = await apiClient.post(`/agent/sessions/${sessionId}/fork`, {
    source_revision_id: sourceRevisionId,
    model_id: modelId,
    ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
  });
  return response.data;
}

export async function submitAgentToolApproval(
  sessionId: string,
  approvalId: string,
  approved: boolean,
): Promise<void> {
  await apiClient.post(`/agent/sessions/${sessionId}/tool-approval`, {
    approval_id: approvalId,
    approved,
  });
}

export async function submitAgentInterruptBatch(
  sessionId: string,
  batchId: string,
  responses: AgentInterruptBatchResponse[],
): Promise<void> {
  await apiClient.post(`/agent/sessions/${sessionId}/interrupt-resume`, {
    batch_id: batchId,
    responses,
  });
}

export async function cancelAgentSession(sessionId: string): Promise<AgentCancelResponse> {
  const response = await apiClient.post(`/agent/sessions/${sessionId}/cancel`);
  return response.data;
}

export async function cancelPendingAgentMessage(
  sessionId: string,
  messageId: string,
): Promise<AgentCancelPendingMessageResponse> {
  const response = await apiClient.post(`/agent/sessions/${sessionId}/pending-message/cancel`, {
    message_id: messageId,
  });
  return response.data;
}
