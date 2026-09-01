import type { TokenUsageState } from "@/lib/agent.types";

export const DEFAULT_CONTEXT_LENGTH = 128000;

export interface SessionTotalUsageState {
  sessionId: string;
  taskId: string | null;
  tokenInput: number;
  tokenOutput: number;
  tokenCache: number;
  cost: number;
}

export interface TaskUsagePayload {
  sessionId: string;
  taskId: string;
  tokenInput: number;
  tokenOutput: number;
  tokenCache: number;
  cost: number;
}

export function createTokenUsageState(contextLength = DEFAULT_CONTEXT_LENGTH): TokenUsageState {
  return {
    tokenInput: 0,
    tokenOutput: 0,
    tokenCache: 0,
    contextInputTokens: 0,
    contextLength,
  };
}

export function createSessionTotalUsageState(
  sessionId = "",
  taskId: string | null = null,
): SessionTotalUsageState {
  return {
    sessionId,
    taskId,
    tokenInput: 0,
    tokenOutput: 0,
    tokenCache: 0,
    cost: 0,
  };
}

export function buildTaskConversationUsage(
  task: Pick<TaskUsagePayload, "tokenInput" | "tokenOutput" | "tokenCache"> & {
    contextInputTokens: number;
  },
  contextLength: number,
): TokenUsageState {
  return {
    tokenInput: task.tokenInput,
    tokenOutput: task.tokenOutput,
    tokenCache: task.tokenCache,
    contextInputTokens: task.contextInputTokens,
    contextLength,
  };
}

export function applyTaskUsageSnapshot(
  current: SessionTotalUsageState,
  payload: TaskUsagePayload,
): SessionTotalUsageState {
  if (current.sessionId && current.sessionId !== payload.sessionId) return current;
  return {
    sessionId: payload.sessionId,
    taskId: payload.taskId,
    tokenInput: payload.tokenInput,
    tokenOutput: payload.tokenOutput,
    tokenCache: payload.tokenCache,
    cost: payload.cost,
  };
}

export function applyTaskUsageDelta(
  current: SessionTotalUsageState,
  payload: TaskUsagePayload,
): SessionTotalUsageState {
  if (current.sessionId && current.sessionId !== payload.sessionId) return current;
  return {
    sessionId: payload.sessionId,
    taskId: payload.taskId,
    tokenInput: current.tokenInput + payload.tokenInput,
    tokenOutput: current.tokenOutput + payload.tokenOutput,
    tokenCache: current.tokenCache + payload.tokenCache,
    cost: current.cost + payload.cost,
  };
}

export function selectConversationUsage({
  usageBySession,
  sessionId,
  isSubagent,
  subagentUsage,
  contextLength,
}: {
  usageBySession: Record<string, TokenUsageState>;
  sessionId: string;
  isSubagent: boolean;
  subagentUsage?: TokenUsageState;
  contextLength?: number;
}): TokenUsageState {
  return (
    usageBySession[sessionId] ??
    (isSubagent ? subagentUsage : undefined) ??
    createTokenUsageState(contextLength)
  );
}

export function getContextUsagePercent(usage: TokenUsageState): number {
  if (usage.contextLength <= 0) return 0;
  return Math.min(100, Math.max(0, (usage.contextInputTokens / usage.contextLength) * 100));
}
