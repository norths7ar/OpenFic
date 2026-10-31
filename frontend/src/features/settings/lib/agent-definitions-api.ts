import * as http from "@/api/generated/openfic";
/**
 * Agent Definitions API
 *
 * 智能体定义 API 客户端，对接后端 /agent-definitions。
 */

import type {
  AgentDefinitionCreateRequest,
  AgentDefinitionResponse,
  AgentToolCategoryResponse,
  AgentDefinitionUpdateRequest,
} from "./agent-definitions.types";

export async function fetchAgentDefinitions(): Promise<AgentDefinitionResponse[]> {
  const response = await http.listDefinitionsApiV1AgentDefinitionsGet();
  return response.data.definitions;
}

export async function fetchAgentDefinition(key: string): Promise<AgentDefinitionResponse> {
  const response = await http.getDefinitionApiV1AgentDefinitionsKeyGet(key);
  return response.data;
}

export async function fetchAgentToolCategories(): Promise<AgentToolCategoryResponse[]> {
  const response = await http.listDefinitionToolCategoriesApiV1AgentDefinitionsToolCategoriesGet();
  return response.data.categories;
}

export async function createAgentDefinition(
  data: AgentDefinitionCreateRequest,
): Promise<AgentDefinitionResponse> {
  const response = await http.createDefinitionApiV1AgentDefinitionsPost(data);
  return response.data;
}

export async function updateAgentDefinition(
  key: string,
  data: AgentDefinitionUpdateRequest,
): Promise<AgentDefinitionResponse> {
  const response = await http.updateDefinitionApiV1AgentDefinitionsKeyPut(key, data);
  return response.data;
}

export async function resetAgentDefinition(key: string): Promise<AgentDefinitionResponse> {
  const response = await http.resetDefinitionApiV1AgentDefinitionsKeyResetPost(key);
  return response.data;
}

export async function deleteAgentDefinition(key: string): Promise<void> {
  await http.deleteDefinitionApiV1AgentDefinitionsKeyDelete(key);
}
