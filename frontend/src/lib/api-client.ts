/**
 * Compatibility facade for legacy feature APIs.
 *
 * New feature APIs should depend on api-transport directly instead of this aggregation module.
 */

import { apiClient } from "./api-transport";

export { apiClient, getApiBaseUrl, getApiUrl, resolveBackendUrl } from "./api-transport";
export {
  applyProjectBundleImport,
  downloadProjectBundle,
  previewProjectBundleImport,
} from "../features/projects/lib/project-bundle-api";
export type {
  ProjectBundlePreviewItem,
  ProjectBundlePreviewResponse,
} from "../features/projects/lib/project-bundle-api";
export {
  createAgentMemory,
  createAgentRule,
  deleteAgentMemory,
  deleteAgentRule,
  fetchAgentMemories,
  fetchAgentRules,
  fetchAgentRuleScopes,
  reorderAgentMemories,
  reorderAgentRules,
  updateAgentMemory,
  updateAgentRule,
} from "../features/assistant/lib/agent-context-api";
export {
  cancelAgentSession,
  cancelPendingAgentMessage,
  cancelSubagentSession,
  compactAgentSession,
  createAgentSession,
  deleteAllTasks,
  deleteTask,
  fetchActiveSubagents,
  fetchAgentSessionState,
  fetchSubagentSession,
  fetchTask,
  fetchTasks,
  forkAgentSession,
  rollbackAgentRevision,
  sendAgentMessage,
  submitAgentInterruptBatch,
  submitAgentQuestionAnswer,
  submitAgentToolApproval,
  subscribeBackgroundEvents,
  subscribeBackgroundProjection,
  updateTask,
  uploadAgentImageAttachment,
} from "../features/assistant/lib/agent-runtime-api";
export type {
  BackgroundEvent,
  BackgroundEventSubscription,
  BackgroundProjectionSubscription,
  BackgroundSnapshot,
} from "../features/assistant/lib/agent-runtime-api";
export {
  searchCommands,
  searchMentionCandidates,
} from "../features/assistant/lib/agent-composer-api";
export {
  batchDeleteCharacters,
  batchFavoriteCharacters,
  createCharacter,
  deleteCharacter,
  fetchCharacter,
  fetchCharactersByProject,
  reorderCharacters,
  searchCharacters,
  updateCharacter,
} from "../features/characters/lib/character-api";
export {
  batchDeleteWorldInfoEntries,
  batchToggleWorldInfoEntries,
  createWorldInfoEntry,
  deleteAllWorldInfoEntries,
  deleteWorldInfo,
  deleteWorldInfoEntry,
  fetchWorldInfoById,
  fetchWorldInfoByProject,
  fetchWorldInfoEntries,
  fetchWorldInfoEntry,
  importWorldInfoEntriesStream,
  moveWorldInfoEntry,
  previewWorldInfoImport,
  searchWorldInfoEntries,
  toggleWorldInfoEntry,
  updateWorldInfoEntry,
} from "../features/world-info/lib/world-info-api";
export {
  compilePromptChain,
  createPromptChainVersion,
  fetchLatestPromptChainVersion,
  fetchPromptChainVersion,
  fetchPromptChainsMetadata,
  fetchPromptChainVersions,
  fetchVersionDiff,
  resetPromptChain,
  searchPromptChainVersionEntries,
} from "../features/prompt-chains/lib/prompt-chain-api";
export {
  createProject,
  deleteProject,
  fetchProject,
  fetchProjects,
  updateProject,
} from "../features/projects/lib/project-api";
export {
  createNote,
  createNoteCategory,
  deleteNote,
  deleteNoteCategory,
  fetchNote,
  fetchNoteTree,
  moveNoteItem,
  reorderMixedNoteItems,
  reorderNoteItems,
  toggleNoteHidden,
  toggleNoteLock,
  updateNote,
  updateNoteCategory,
} from "../features/writing/lib/note-api";
export {
  createChapter,
  createVolume,
  deleteChapter,
  deleteVolume,
  fetchChapter,
  fetchChapters,
  fetchVolume,
  fetchVolumes,
  moveChapterToVolume,
  moveVolume,
  reorderChapters,
  updateChapter,
  updateVolume,
} from "../features/writing/lib/chapter-volume-api";
export {
  cancelChapterExport,
  createChapterExport,
  fetchChapterExport,
} from "../features/writing/lib/chapter-export-api";
export { fetchChapterContext } from "../features/writing/lib/chapter-context-api";
export type {
  BuiltContextResponse,
  ContextPartResponse,
} from "../features/writing/lib/chapter-context-api";
export {
  searchChapters,
  searchNotes,
  transformHighlightParts,
} from "../features/writing/lib/writing-search-api";
export type {
  ChapterSearchMatch,
  ChapterSearchResponse,
  ChapterSearchResultItem,
  HighlightPart,
  NoteSearchMatch,
  NoteSearchResponse,
  NoteSearchResultItem,
} from "../features/writing/lib/writing-search-api";

// 健康检查类型
export interface HealthResponse {
  status: string;
  version: string;
}

export interface AuthStatusResponse {
  enabled: boolean;
  authenticated: boolean;
}

export interface AuthPreferencesResponse {
  language: string;
  theme: string;
  font_family: string;
  code_font_family: string;
  base_font_size: number;
  editor_font_size: number;
}

export interface AuthLoginRequest {
  password: string;
  trust_device: boolean;
}

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
  const response = await apiClient.get<AuthStatusResponse>("/auth/status");
  return response.data;
}

export async function fetchAuthPreferences(): Promise<AuthPreferencesResponse> {
  const response = await apiClient.get<AuthPreferencesResponse>("/auth/preferences");
  return response.data;
}

export async function loginWithPassword(payload: AuthLoginRequest): Promise<AuthStatusResponse> {
  const response = await apiClient.post<AuthStatusResponse>("/auth/login", payload);
  return response.data;
}

// 健康检查 API
export async function checkHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>("/health");
  return response.data;
}

export {
  createSkill,
  createSkillReferenceDoc,
  deleteSkill,
  deleteSkillReferenceDoc,
  fetchSkill,
  fetchSkillReferenceDocs,
  fetchSkills,
  forkSkill,
  importSkill,
  toggleSkill,
  updateSkill,
  updateSkillReferenceDoc,
} from "../features/settings/lib/skills-api";
export {
  cancelBackgroundJob,
  deleteChapterSummaries,
  deleteLongTermSummaries,
  enqueueSummary,
  fetchChapterSummaryList,
  fetchLongTermSummariesPage,
  transformSummaryRealtimeSnapshot,
} from "../features/writing/lib/summary-api";
export type {
  ChapterSummaryListItem,
  ChapterSummaryListResponse,
  EnqueueSummaryRequest,
  EnqueueSummaryResponse,
  LongTermSummaryListItem,
  LongTermSummaryListResponse,
  MissingChapterSummaryItem,
  MissingLongTermSummaryItem,
  SkippedChapterSummaryItem,
  SummaryBackgroundJobItem,
  SummaryBatchProgressItem,
  SummaryMaintenance,
  SummaryPanelResponse,
  SummaryRealtimeSnapshot,
  SummaryStatus,
  SummaryStatusItem,
} from "../features/writing/lib/summary-api";
// ============================================
// Model API
// ============================================

import type { Model, ModelResponse } from "./model.types";

/**
 * 后端响应字段转换（snake_case -> camelCase）
 */
function transformModel(raw: ModelResponse): Model {
  return {
    id: raw.id,
    name: raw.name,
    remark: raw.remark,
    providerId: raw.provider_id,
    modelId: raw.model_id,
    taskType: raw.task_type,
    temperature: raw.temperature,
    topP: raw.top_p,
    topK: raw.top_k,
    minP: raw.min_p,
    topA: raw.top_a,
    frequencyPenalty: raw.frequency_penalty,
    presencePenalty: raw.presence_penalty,
    repetitionPenalty: raw.repetition_penalty,
    maxTokens: raw.max_tokens,
    contextLength: raw.context_length ?? 128000,
    inputPrice: raw.input_price ?? 0,
    outputPrice: raw.output_price ?? 0,
    cacheReadPrice: raw.cache_read_price ?? 0,
    cacheWritePrice: raw.cache_write_price ?? 0,
    dimensions: raw.dimensions,
    isBuiltin: raw.is_builtin ?? false,
    isEnabled: raw.is_enabled ?? true,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

/**
 * 获取所有模型列表
 */
export async function fetchModels(): Promise<Model[]> {
  const response = await apiClient.get<ModelResponse[]>("/models");
  return response.data.map(transformModel);
}
