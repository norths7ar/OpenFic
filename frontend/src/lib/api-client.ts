/**
 * Compatibility facade for legacy feature APIs.
 *
 * New feature APIs should depend on api-transport directly instead of this aggregation module.
 */

import { apiClient, resolveBackendUrl } from "./api-transport";
import type { DocumentType } from "./note.types";

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

// ============================================
// Chapter Export API
// ============================================

import type { ChapterExport, ChapterExportCreate } from "./chapter-export.types";
import type {
  SkillReferenceDoc,
  SkillReferenceDocCreate,
  SkillReferenceDocUpdate,
} from "./skill-reference-doc.types";
import type {
  Skill,
  SkillCreate,
  SkillImportResult,
  SkillListParams,
  SkillListResponse,
  SkillUpdate,
} from "./skill.types";

function transformChapterExport(raw: Record<string, unknown>): ChapterExport {
  return {
    id: raw.id as string,
    status: raw.status as string,
    filename: raw.filename as string,
    mode: raw.mode as ChapterExport["mode"],
    volumeCount: Number(raw.volume_count ?? 0),
    chapterCount: Number(raw.chapter_count ?? 0),
    wordCount: Number(raw.word_count ?? 0),
    chapterIds: Array.isArray(raw.chapter_ids)
      ? raw.chapter_ids.filter((chapterId): chapterId is string => typeof chapterId === "string")
      : [],
    current: Number(raw.current ?? 0),
    total: Number(raw.total ?? 0),
    stage: typeof raw.stage === "string" ? raw.stage : null,
    chapterTitle: typeof raw.chapter_title === "string" ? raw.chapter_title : null,
    expiresAt: typeof raw.expires_at === "string" ? raw.expires_at : null,
    downloadUrl: resolveBackendUrl(raw.download_url as string | null | undefined),
    errorMessage: typeof raw.error_message === "string" ? raw.error_message : null,
  };
}

export async function createChapterExport(
  projectId: string,
  data: ChapterExportCreate,
): Promise<ChapterExport> {
  const response = await apiClient.post(`/projects/${projectId}/chapter-exports`, {
    selected_volume_ids: data.selectedVolumeIds,
    included_chapter_ids: data.includedChapterIds,
    excluded_chapter_ids: data.excludedChapterIds,
    local_date: data.localDate,
  });
  return transformChapterExport(response.data);
}

export async function fetchChapterExport(projectId: string, jobId: string): Promise<ChapterExport> {
  const response = await apiClient.get(`/projects/${projectId}/chapter-exports/${jobId}`);
  return transformChapterExport(response.data);
}

export async function cancelChapterExport(
  projectId: string,
  jobId: string,
): Promise<ChapterExport> {
  const response = await apiClient.post(`/projects/${projectId}/chapter-exports/${jobId}/cancel`);
  return transformChapterExport(response.data);
}

function transformSkill(raw: Record<string, unknown>): Skill {
  return {
    id: raw.id as string,
    name: raw.name as string,
    summary: raw.summary as string,
    content: raw.content as string,
    isEnabled: raw.is_enabled as boolean,
    isComplete: raw.is_complete as boolean,
    source: raw.source as "builtin" | "custom",
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchSkills(params?: SkillListParams): Promise<SkillListResponse> {
  const response = await apiClient.get("/skills", {
    params: {
      page: params?.page ?? 1,
      page_size: params?.pageSize ?? 100,
    },
  });
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map(transformSkill),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function fetchSkill(skillDbId: string): Promise<Skill> {
  const response = await apiClient.get(`/skills/${skillDbId}`);
  return transformSkill(response.data);
}

export async function createSkill(data: SkillCreate): Promise<Skill> {
  const response = await apiClient.post("/skills", {
    name: data.name,
    summary: data.summary,
    content: data.content,
    is_enabled: data.isEnabled ?? false,
  });
  return transformSkill(response.data);
}

export async function importSkill(file: File): Promise<SkillImportResult> {
  const formData = new FormData();
  formData.append("files", file);
  const response = await apiClient.post("/skills/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return {
    skill: transformSkill(response.data.skill),
    referenceDocs: (response.data.reference_docs as Record<string, unknown>[]).map(
      transformSkillReferenceDoc,
    ),
    isRecognized: response.data.is_recognized as boolean,
  };
}

export async function updateSkill(skillDbId: string, data: SkillUpdate): Promise<Skill> {
  const response = await apiClient.patch(`/skills/${skillDbId}`, {
    name: data.name,
    summary: data.summary,
    content: data.content,
    is_enabled: data.isEnabled,
  });
  return transformSkill(response.data);
}

export async function toggleSkill(skillDbId: string): Promise<Skill> {
  const response = await apiClient.post(`/skills/${skillDbId}/toggle`);
  return transformSkill(response.data);
}

export async function forkSkill(skillDbId: string): Promise<Skill> {
  const response = await apiClient.post(`/skills/${skillDbId}/fork`);
  return transformSkill(response.data);
}

export async function deleteSkill(skillDbId: string): Promise<void> {
  await apiClient.delete(`/skills/${skillDbId}`);
}

// ============================================
// Skill Reference Docs API
// ============================================

function transformSkillReferenceDoc(raw: Record<string, unknown>): SkillReferenceDoc {
  return {
    id: raw.id as string,
    title: raw.title as string,
    content: raw.content as string,
    tokens: raw.tokens as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchSkillReferenceDocs(skillDbId: string): Promise<SkillReferenceDoc[]> {
  const response = await apiClient.get(`/skills/${skillDbId}/reference-docs`);
  return (response.data as Record<string, unknown>[]).map(transformSkillReferenceDoc);
}

export async function createSkillReferenceDoc(
  skillDbId: string,
  data: SkillReferenceDocCreate,
): Promise<SkillReferenceDoc> {
  const response = await apiClient.post(`/skills/${skillDbId}/reference-docs`, {
    title: data.title,
    content: data.content,
  });
  return transformSkillReferenceDoc(response.data);
}

export async function updateSkillReferenceDoc(
  skillDbId: string,
  docId: string,
  data: SkillReferenceDocUpdate,
): Promise<SkillReferenceDoc> {
  const response = await apiClient.patch(`/skills/${skillDbId}/reference-docs/${docId}`, {
    title: data.title,
    content: data.content,
  });
  return transformSkillReferenceDoc(response.data);
}

export async function deleteSkillReferenceDoc(skillDbId: string, docId: string): Promise<void> {
  await apiClient.delete(`/skills/${skillDbId}/reference-docs/${docId}`);
}

// ============================================
// Chapter Context API
// ============================================

/**
 * 上下文部分响应
 */
export interface ContextPartResponse {
  content: string;
  token_count: number;
  chapter_range: [number, number];
}

/**
 * 构建的上下文响应
 */
export interface BuiltContextResponse {
  latest_field: ContextPartResponse;
  near_field: ContextPartResponse;
  mid_field: ContextPartResponse;
  far_field: ContextPartResponse;
}

/**
 * 获取构建的章节上下文
 */
export async function fetchChapterContext(
  projectId: string,
  currentOrder: number,
): Promise<BuiltContextResponse> {
  const response = await apiClient.get<BuiltContextResponse>(
    `/projects/${projectId}/chapter-context/context`,
    {
      params: {
        current_order: currentOrder,
      },
    },
  );
  return response.data;
}

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
export interface ChapterSearchMatch {
  lineNumber: number;
  lineText: string;
}

export interface ChapterSearchResultItem {
  chapterId: string;
  chapterTitle: string;
  volumeTitle: string;
  matches: ChapterSearchMatch[];
}

export interface ChapterSearchResponse {
  results: ChapterSearchResultItem[];
  totalChapters: number;
  totalMatches: number;
}

export async function searchChapters(
  projectId: string,
  query: string,
): Promise<ChapterSearchResponse> {
  const response = await apiClient.get(`/projects/${projectId}/chapters/search`, {
    params: { q: query },
  });
  const data = response.data as Record<string, unknown>;
  return {
    results: ((data.results as Record<string, unknown>[]) ?? []).map(
      (r: Record<string, unknown>) => ({
        chapterId: r.chapter_id as string,
        chapterTitle: r.chapter_title as string,
        volumeTitle: r.volume_title as string,
        matches: ((r.matches as Record<string, unknown>[]) ?? []).map(
          (m: Record<string, unknown>) => ({
            lineNumber: m.line_number as number,
            lineText: m.line_text as string,
          }),
        ),
      }),
    ),
    totalChapters: data.total_chapters as number,
    totalMatches: data.total_matches as number,
  };
}

export interface NoteSearchMatch {
  lineNumber: number;
  lineText: string;
}

export interface NoteSearchResultItem {
  noteId: string;
  noteTitle: string;
  categoryPath: string;
  matches: NoteSearchMatch[];
}

export interface NoteSearchResponse {
  results: NoteSearchResultItem[];
  totalNotes: number;
  totalMatches: number;
}

export async function searchNotes(
  projectId: string,
  query: string,
  documentType: DocumentType = "note",
): Promise<NoteSearchResponse> {
  const response = await apiClient.get(`/projects/${projectId}/notes/search`, {
    params: { q: query, document_type: documentType },
  });
  const data = response.data as Record<string, unknown>;
  return {
    results: ((data.results as Record<string, unknown>[]) ?? []).map(
      (r: Record<string, unknown>) => ({
        noteId: r.note_id as string,
        noteTitle: r.note_title as string,
        categoryPath: r.category_path as string,
        matches: ((r.matches as Record<string, unknown>[]) ?? []).map(
          (m: Record<string, unknown>) => ({
            lineNumber: m.line_number as number,
            lineText: m.line_text as string,
          }),
        ),
      }),
    ),
    totalNotes: data.total_notes as number,
    totalMatches: data.total_matches as number,
  };
}

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
