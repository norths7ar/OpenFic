import i18n from "@/i18n";

/**
 * Agent Definition Types
 *
 * 智能体定义前端类型，对齐后端 /agent-definitions API。
 */

export type AgentDefinitionResponse = import("@/api/generated/models").AgentDefinitionResponse;

export type AgentDefinitionCreateRequest =
  import("@/api/generated/models").AgentDefinitionCreateRequest;

export type AgentDefinitionUpdateRequest =
  import("@/api/generated/models").AgentDefinitionUpdateRequest;

export type AgentDefinitionListResponse =
  import("@/api/generated/models").AgentDefinitionListResponse;

export type AgentToolCategoryResponse = import("@/api/generated/models").AgentToolCategoryResponse;

export type AgentToolCategoryListResponse =
  import("@/api/generated/models").AgentToolCategoryListResponse;

export const SYSTEM_DEFAULT_MODEL_REFERENCE = "__system_default_model__";
export const SYSTEM_LIGHT_MODEL_REFERENCE = "__system_light_model__";

const AGENT_KIND_LABEL_KEYS: Record<string, string> = {
  primary: "settings.agentsKindPrimary",
  subagent: "settings.agentsKindSubagent",
};

export function getAgentKindOptions(): Array<{ value: "primary" | "subagent"; label: string }> {
  return [
    { value: "primary", label: i18n.t("settings.agentsKindPrimary") },
    { value: "subagent", label: i18n.t("settings.agentsKindSubagent") },
  ];
}

export function getAgentKindLabel(kind: string): string {
  return i18n.t(AGENT_KIND_LABEL_KEYS[kind] ?? kind, { defaultValue: kind });
}
