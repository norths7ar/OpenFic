import * as http from "@/api/generated/openfic";
/**
 * Settings API
 *
 * 设置 API 客户端。
 */

import type {
  AgentToolMetadata,
  AuditDetailsStorage,
  Settings,
  SettingsResponse,
  SettingsUpdateRequest,
} from "./settings.types";
import {
  DEFAULT_CODE_FONT_FAMILY,
  getSupportedCodeFontFamily,
  getSupportedFontFamily,
} from "./settings.types";

/**
 * 后端响应字段转换（snake_case -> camelCase）
 */
export function transformSettings(raw: SettingsResponse): Settings {
  return {
    language: raw.language as Settings["language"],
    theme: raw.theme as Settings["theme"],
    fontFamily: getSupportedFontFamily(raw.font_family),
    codeFontFamily: getSupportedCodeFontFamily(raw.code_font_family || DEFAULT_CODE_FONT_FAMILY),
    baseFontSize: raw.base_font_size ?? 14,
    editorFontSize: raw.editor_font_size ?? 16,
    defaultModel: raw.default_model || "",
    lightModel: raw.light_model || "",
    defaultEmbeddingModel: raw.default_embedding_model || "",
    indexMode: raw.index_mode ?? "off",
    indexEnabledProjects: raw.index_enabled_projects ?? [],
    indexChunkSize: raw.index_chunk_size ?? 800,
    indexChunkOverlap: raw.index_chunk_overlap ?? 100,
    indexAutoStrategy: raw.index_auto_strategy ?? "off",
    indexRerankEnabled: raw.index_rerank_enabled ?? false,
    defaultRerankModel: raw.default_rerank_model || "",
    agentBypassToolApproval: raw.agent_bypass_tool_approval ?? false,
    agentToolPermissions: (raw.agent_tool_permissions || []).map((item) => ({
      toolName: item.tool_name,
      mode: item.mode,
    })),
    auditPersistDetails: raw.audit_persist_details ?? false,
    compressSystemPrompts: raw.compress_system_prompts ?? false,
    editorAutoIndent: raw.editor_auto_indent ?? true,
    editorAutoConvertPunctuation: raw.editor_auto_convert_punctuation ?? false,
    editorAutoPairSymbols: raw.editor_auto_pair_symbols ?? false,
    editorShowLineNumbers: raw.editor_show_line_numbers ?? false,
  };
}

/**
 * 获取设置
 */
export async function fetchSettings(): Promise<Settings> {
  const response = await http.getSettingsApiV1SettingsGet();
  return transformSettings(response.data);
}

/**
 * 更新设置
 */
export async function updateSettings(data: SettingsUpdateRequest): Promise<Settings> {
  const response = await http.updateSettingsApiV1SettingsPut(data);
  return transformSettings(response.data);
}

export async function fetchAgentTools(): Promise<AgentToolMetadata[]> {
  const response = await http.listAgentToolsApiV1AgentToolsGet();
  return response.data.map((tool) => ({
    key: tool.key,
    isReadonly: tool.is_readonly,
  }));
}

export async function fetchAuditDetailsStorage(): Promise<AuditDetailsStorage> {
  const response = await http.getAuditDetailsStorageApiV1SettingsAuditDetailsStorageGet();
  return {
    detailRecordsCount: response.data.detail_records_count,
    detailBytes: response.data.detail_bytes,
  };
}

export async function clearAuditDetails(): Promise<void> {
  await http.clearAuditDetailsApiV1SettingsAuditDetailsDelete();
}
