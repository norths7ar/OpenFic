import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
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

function transformAgentRule(raw: schemas.AgentRuleResponse): AgentRule {
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
  const response = await http.listScopesApiV1AgentRulesScopesGet();
  const data = response.data;
  return {
    items: data.items.map((raw) => ({
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
  const response = await http.listRulesApiV1AgentRulesGet({
    page: params?.page ?? 1,
    page_size: params?.pageSize ?? 100,
    scope: params?.scope ?? "global",
    project_id: params?.projectId ?? undefined,
  });
  const data = response.data;
  return {
    items: data.items.map(transformAgentRule),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function createAgentRule(data: AgentRuleCreate): Promise<AgentRule> {
  const response = await http.createRuleApiV1AgentRulesPost({
    title: data.title,
    content: data.content,
    scope: data.scope ?? "global",
    project_id: data.projectId ?? null,
  });
  return transformAgentRule(response.data);
}

export async function updateAgentRule(ruleId: string, data: AgentRuleUpdate): Promise<AgentRule> {
  const response = await http.updateRuleApiV1AgentRulesRuleIdPatch(ruleId, {
    title: data.title,
    content: data.content,
  });
  return transformAgentRule(response.data);
}

export async function deleteAgentRule(ruleId: string): Promise<void> {
  await http.deleteRuleApiV1AgentRulesRuleIdDelete(ruleId);
}

export async function reorderAgentRules(ruleIds: string[]): Promise<AgentRule[]> {
  const response = await http.reorderRulesApiV1AgentRulesReorderPost({
    rule_ids: ruleIds,
  });
  return response.data.map(transformAgentRule);
}

function transformAgentMemory(raw: schemas.AgentMemoryResponse): AgentMemory {
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
  const response = await http.listMemoriesApiV1AgentMemoriesGet({
    page: params?.page ?? 1,
    page_size: params?.pageSize ?? 100,
  });
  const data = response.data;
  return {
    items: data.items.map(transformAgentMemory),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function createAgentMemory(data: AgentMemoryCreate): Promise<AgentMemory> {
  const response = await http.createMemoryApiV1AgentMemoriesPost({
    content: data.content,
  });
  return transformAgentMemory(response.data);
}

export async function updateAgentMemory(
  memoryId: string,
  data: AgentMemoryUpdate,
): Promise<AgentMemory> {
  const response = await http.updateMemoryApiV1AgentMemoriesMemoryIdPatch(memoryId, {
    content: data.content,
  });
  return transformAgentMemory(response.data);
}

export async function deleteAgentMemory(memoryId: string): Promise<void> {
  await http.deleteMemoryApiV1AgentMemoriesMemoryIdDelete(memoryId);
}

export async function reorderAgentMemories(memoryIds: string[]): Promise<AgentMemory[]> {
  const response = await http.reorderMemoriesApiV1AgentMemoriesReorderPost({
    memory_ids: memoryIds,
  });
  return response.data.map(transformAgentMemory);
}
