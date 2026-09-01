import type {
  AgentMemory,
  AgentMemoryCreate,
  AgentMemoryListParams,
  AgentMemoryListResponse,
  AgentMemoryUpdate,
} from "@/lib/agent-memory.types";
import type {
  AgentRule,
  AgentRuleCreate,
  AgentRuleListParams,
  AgentRuleListResponse,
  AgentRuleScopeListResponse,
  AgentRuleUpdate,
} from "@/lib/agent-rule.types";
import { apiClient } from "@/lib/api-transport";

function transformAgentRule(raw: Record<string, unknown>): AgentRule {
  return {
    id: raw.id as string,
    title: raw.title as string,
    content: raw.content as string,
    scope: (raw.scope as string) ?? "global",
    projectId: (raw.project_id as string | null) ?? null,
    tokenCount: (raw.token_count as number) ?? 0,
    orderIndex: (raw.order_index as number) ?? 0,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchAgentRuleScopes(): Promise<AgentRuleScopeListResponse> {
  const response = await apiClient.get("/agent-rules/scopes");
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map((raw) => ({
      scope: raw.scope as string,
      projectId: (raw.project_id as string | null) ?? null,
      title: raw.title as string,
      ruleCount: (raw.rule_count as number) ?? 0,
    })),
  };
}

export async function fetchAgentRules(
  params?: AgentRuleListParams,
): Promise<AgentRuleListResponse> {
  const response = await apiClient.get("/agent-rules", {
    params: {
      page: params?.page ?? 1,
      page_size: params?.pageSize ?? 100,
      scope: params?.scope ?? "global",
      project_id: params?.projectId ?? undefined,
    },
  });
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map(transformAgentRule),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function createAgentRule(data: AgentRuleCreate): Promise<AgentRule> {
  const response = await apiClient.post("/agent-rules", {
    title: data.title,
    content: data.content,
    scope: data.scope ?? "global",
    project_id: data.projectId ?? null,
  });
  return transformAgentRule(response.data);
}

export async function updateAgentRule(ruleId: string, data: AgentRuleUpdate): Promise<AgentRule> {
  const response = await apiClient.patch(`/agent-rules/${ruleId}`, {
    title: data.title,
    content: data.content,
  });
  return transformAgentRule(response.data);
}

export async function deleteAgentRule(ruleId: string): Promise<void> {
  await apiClient.delete(`/agent-rules/${ruleId}`);
}

export async function reorderAgentRules(ruleIds: string[]): Promise<AgentRule[]> {
  const response = await apiClient.post("/agent-rules/reorder", {
    rule_ids: ruleIds,
  });
  return (response.data as Record<string, unknown>[]).map(transformAgentRule);
}

function transformAgentMemory(raw: Record<string, unknown>): AgentMemory {
  return {
    id: raw.id as string,
    content: raw.content as string,
    orderIndex: (raw.order_index as number) ?? 0,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchAgentMemories(
  params?: AgentMemoryListParams,
): Promise<AgentMemoryListResponse> {
  const response = await apiClient.get("/agent-memories", {
    params: {
      page: params?.page ?? 1,
      page_size: params?.pageSize ?? 100,
    },
  });
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map(transformAgentMemory),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function createAgentMemory(data: AgentMemoryCreate): Promise<AgentMemory> {
  const response = await apiClient.post("/agent-memories", {
    content: data.content,
  });
  return transformAgentMemory(response.data);
}

export async function updateAgentMemory(
  memoryId: string,
  data: AgentMemoryUpdate,
): Promise<AgentMemory> {
  const response = await apiClient.patch(`/agent-memories/${memoryId}`, {
    content: data.content,
  });
  return transformAgentMemory(response.data);
}

export async function deleteAgentMemory(memoryId: string): Promise<void> {
  await apiClient.delete(`/agent-memories/${memoryId}`);
}

export async function reorderAgentMemories(memoryIds: string[]): Promise<AgentMemory[]> {
  const response = await apiClient.post("/agent-memories/reorder", {
    memory_ids: memoryIds,
  });
  return (response.data as Record<string, unknown>[]).map(transformAgentMemory);
}
