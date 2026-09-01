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

export type SummaryStatus = "not_generated" | "queued" | "running" | "ready" | "failed";

export interface LongTermSummaryListItem {
  startOrder: number;
  endOrder: number;
  startVolumeTitle: string | null;
  startChapterTitle: string;
  endVolumeTitle: string | null;
  endChapterTitle: string;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  startTime: string;
  endTime: string;
  summary: string;
  errorMessage: string | null;
  updatedAt: string | null;
}

export interface SummaryStatusItem {
  chapterId: string;
  volumeId: string | null;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  updatedAt: string | null;
}

export interface SummaryPanelResponse {
  maintenance: SummaryMaintenance;
}

export interface SummaryRealtimeSnapshot {
  projectId: string;
  projectRevision: number | null;
  summary: {
    statuses: SummaryStatusItem[];
    maintenance: SummaryMaintenance;
  };
}

export interface ChapterSummaryListItem {
  chapterId: string;
  chapterOrder: number;
  volumeId: string | null;
  volumeTitle: string | null;
  volumeOrder: number | null;
  chapterTitle: string;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  startTime: string;
  endTime: string;
  characters: string[];
  locations: string[];
  summary: string;
  errorMessage: string | null;
  updatedAt: string | null;
}

export interface ChapterSummaryListResponse {
  items: ChapterSummaryListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface LongTermSummaryListResponse {
  items: LongTermSummaryListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface MissingChapterSummaryItem {
  chapterId: string;
  chapterOrder: number;
  volumeId: string | null;
  volumeTitle: string | null;
  volumeOrder: number | null;
  chapterTitle: string;
  wordCount: number;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  progressMessage: string | null;
}

export interface MissingLongTermSummaryItem {
  startOrder: number;
  endOrder: number;
  startVolumeTitle: string | null;
  startChapterTitle: string;
  endVolumeTitle: string | null;
  endChapterTitle: string;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  progressMessage: string | null;
}

export interface SkippedChapterSummaryItem {
  chapterId: string;
  chapterOrder: number;
  volumeId: string | null;
  volumeTitle: string | null;
  volumeOrder: number | null;
  chapterTitle: string;
  wordCount: number;
}

export interface SummaryBackgroundJobItem {
  jobId: string;
  jobType: "chapter_summary" | "long_term_summary" | "summary_batch";
  status: string;
  chapterId: string | null;
  summaryId: string | null;
  startOrder: number | null;
  endOrder: number | null;
  progressCurrent: number;
  progressTotal: number | null;
  progressMessage: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SummaryBatchProgressItem {
  jobId: string;
  status: string;
  progressCurrent: number;
  progressTotal: number | null;
  progressPercent: number | null;
  progressMessage: string | null;
  totalItemCount: number;
  completedItemCount: number;
  runningItemCount: number;
  queuedItemCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface SummaryMaintenance {
  autoGenerationBlocked: boolean;
  blockReasonCode: string | null;
  blockReasonParams: Record<string, number | string> | null;
  missingOrFailedChapterSummaries: MissingChapterSummaryItem[];
  missingOrFailedLongTermSummaries: MissingLongTermSummaryItem[];
  skippedChapterSummaries: SkippedChapterSummaryItem[];
  batchProgress: SummaryBatchProgressItem | null;
  activeJobs: SummaryBackgroundJobItem[];
}

export interface EnqueueSummaryRequest {
  summaryType: "chapter" | "long_term" | "all";
  chapterId?: string;
  startOrder?: number;
  endOrder?: number;
}

export interface EnqueueSummaryResponse {
  summaryId: string | null;
  status: string;
  jobId: string | null;
  itemCount: number;
}

function transformSummaryStatusItem(raw: Record<string, unknown>): SummaryStatusItem {
  return {
    chapterId: raw.chapter_id as string,
    volumeId: (raw.volume_id as string | null) ?? null,
    status: raw.status as SummaryStatus,
    isStale: Boolean(raw.is_stale),
    summaryId: raw.summary_id as string | null,
    updatedAt: raw.updated_at as string | null,
  };
}

function transformLongTermSummaryListItem(raw: Record<string, unknown>): LongTermSummaryListItem {
  return {
    startOrder: Number(raw.start_order ?? 0),
    endOrder: Number(raw.end_order ?? 0),
    startVolumeTitle: (raw.start_volume_title as string | null) ?? null,
    startChapterTitle: (raw.start_chapter_title as string) || "",
    endVolumeTitle: (raw.end_volume_title as string | null) ?? null,
    endChapterTitle: (raw.end_chapter_title as string) || "",
    status: raw.status as SummaryStatus,
    isStale: Boolean(raw.is_stale),
    summaryId: raw.summary_id as string | null,
    startTime: (raw.start_time as string) || "",
    endTime: (raw.end_time as string) || "",
    summary: (raw.summary as string) || "",
    errorMessage: raw.error_message as string | null,
    updatedAt: raw.updated_at as string | null,
  };
}

function transformChapterSummaryListItem(raw: Record<string, unknown>): ChapterSummaryListItem {
  return {
    chapterId: raw.chapter_id as string,
    chapterOrder: Number(raw.chapter_order ?? 0),
    volumeId: (raw.volume_id as string | null) ?? null,
    volumeTitle: (raw.volume_title as string | null) ?? null,
    volumeOrder: raw.volume_order == null ? null : Number(raw.volume_order),
    chapterTitle: (raw.chapter_title as string) || "未命名章节",
    status: raw.status as SummaryStatus,
    isStale: Boolean(raw.is_stale),
    summaryId: raw.summary_id as string | null,
    startTime: (raw.start_time as string) || "",
    endTime: (raw.end_time as string) || "",
    characters: (raw.characters as string[]) || [],
    locations: (raw.locations as string[]) || [],
    summary: (raw.summary as string) || "",
    errorMessage: raw.error_message as string | null,
    updatedAt: raw.updated_at as string | null,
  };
}

function transformSummaryMaintenance(raw: Record<string, unknown>): SummaryMaintenance {
  return {
    autoGenerationBlocked: Boolean(raw.auto_generation_blocked),
    blockReasonCode: (raw.block_reason_code as string | null) ?? null,
    blockReasonParams: (raw.block_reason_params as Record<string, number | string> | null) ?? null,
    missingOrFailedChapterSummaries: (
      (raw.missing_or_failed_chapter_summaries as Record<string, unknown>[]) || []
    ).map((item) => ({
      chapterId: item.chapter_id as string,
      chapterOrder: item.chapter_order as number,
      volumeId: (item.volume_id as string | null) ?? null,
      volumeTitle: (item.volume_title as string | null) ?? null,
      volumeOrder: item.volume_order == null ? null : Number(item.volume_order),
      chapterTitle: item.chapter_title as string,
      wordCount: Number(item.word_count ?? 0),
      status: item.status as SummaryStatus,
      isStale: Boolean(item.is_stale),
      summaryId: item.summary_id as string | null,
      progressMessage: (item.progress_message as string | null) ?? null,
    })),
    missingOrFailedLongTermSummaries: (
      (raw.missing_or_failed_long_term_summaries as Record<string, unknown>[]) || []
    ).map((item) => ({
      startOrder: item.start_order as number,
      endOrder: item.end_order as number,
      startVolumeTitle: (item.start_volume_title as string | null) ?? null,
      startChapterTitle: (item.start_chapter_title as string) || "",
      endVolumeTitle: (item.end_volume_title as string | null) ?? null,
      endChapterTitle: (item.end_chapter_title as string) || "",
      status: item.status as SummaryStatus,
      isStale: Boolean(item.is_stale),
      summaryId: item.summary_id as string | null,
      progressMessage: (item.progress_message as string | null) ?? null,
    })),
    skippedChapterSummaries: (
      (raw.skipped_chapter_summaries as Record<string, unknown>[]) || []
    ).map((item) => ({
      chapterId: item.chapter_id as string,
      chapterOrder: Number(item.chapter_order ?? 0),
      volumeId: (item.volume_id as string | null) ?? null,
      volumeTitle: (item.volume_title as string | null) ?? null,
      volumeOrder: item.volume_order == null ? null : Number(item.volume_order),
      chapterTitle: (item.chapter_title as string) || "未命名章节",
      wordCount: Number(item.word_count ?? 0),
    })),
    batchProgress: raw.batch_progress
      ? {
          jobId: (raw.batch_progress as Record<string, unknown>).job_id as string,
          status: (raw.batch_progress as Record<string, unknown>).status as string,
          progressCurrent: Number(
            (raw.batch_progress as Record<string, unknown>).progress_current ?? 0,
          ),
          progressTotal:
            (raw.batch_progress as Record<string, unknown>).progress_total == null
              ? null
              : Number((raw.batch_progress as Record<string, unknown>).progress_total),
          progressPercent:
            (raw.batch_progress as Record<string, unknown>).progress_percent == null
              ? null
              : Number((raw.batch_progress as Record<string, unknown>).progress_percent),
          progressMessage:
            ((raw.batch_progress as Record<string, unknown>).progress_message as string | null) ??
            null,
          totalItemCount: Number(
            (raw.batch_progress as Record<string, unknown>).total_item_count ?? 0,
          ),
          completedItemCount: Number(
            (raw.batch_progress as Record<string, unknown>).completed_item_count ?? 0,
          ),
          runningItemCount: Number(
            (raw.batch_progress as Record<string, unknown>).running_item_count ?? 0,
          ),
          queuedItemCount: Number(
            (raw.batch_progress as Record<string, unknown>).queued_item_count ?? 0,
          ),
          createdAt: (raw.batch_progress as Record<string, unknown>).created_at as string,
          updatedAt: (raw.batch_progress as Record<string, unknown>).updated_at as string,
        }
      : null,
    activeJobs: ((raw.active_jobs as Record<string, unknown>[]) || []).map((item) => ({
      jobId: item.job_id as string,
      jobType: item.job_type as "chapter_summary" | "long_term_summary" | "summary_batch",
      status: item.status as string,
      chapterId: (item.chapter_id as string | null) ?? null,
      summaryId: (item.summary_id as string | null) ?? null,
      startOrder: (item.start_order as number | null) ?? null,
      endOrder: (item.end_order as number | null) ?? null,
      progressCurrent: Number(item.progress_current ?? 0),
      progressTotal: item.progress_total == null ? null : Number(item.progress_total),
      progressMessage: (item.progress_message as string | null) ?? null,
      errorMessage: (item.error_message as string | null) ?? null,
      createdAt: item.created_at as string,
      updatedAt: item.updated_at as string,
    })),
  };
}

export function transformSummaryRealtimeSnapshot(
  raw: Record<string, unknown>,
): SummaryRealtimeSnapshot {
  const summary = (raw.summary as Record<string, unknown>) || {};
  return {
    projectId: raw.project_id as string,
    projectRevision: raw.project_revision == null ? null : Number(raw.project_revision),
    summary: {
      statuses: ((summary.statuses as Record<string, unknown>[]) || []).map(
        transformSummaryStatusItem,
      ),
      maintenance: transformSummaryMaintenance(
        (summary.maintenance as Record<string, unknown>) || {},
      ),
    },
  };
}

export async function fetchChapterSummaryList(
  projectId: string,
  page: number,
  pageSize = 20,
  signal?: AbortSignal,
  volumeId?: string | null,
  query?: string,
): Promise<ChapterSummaryListResponse> {
  const response = await apiClient.get<Record<string, unknown>>(
    `/projects/${projectId}/chapter-context/summaries/chapters`,
    {
      params: {
        page,
        page_size: pageSize,
        ...(volumeId ? { volume_id: volumeId } : {}),
        ...(query ? { q: query } : {}),
      },
      signal,
    },
  );
  return {
    items: ((response.data.items as Record<string, unknown>[]) || []).map(
      transformChapterSummaryListItem,
    ),
    total: Number(response.data.total ?? 0),
    page: Number(response.data.page ?? page),
    pageSize: Number(response.data.page_size ?? pageSize),
  };
}

export async function deleteChapterSummaries(
  projectId: string,
  chapterIds: string[],
): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/chapter-context/summaries/chapters`, {
    data: {
      chapter_ids: chapterIds,
    },
  });
}

export async function deleteLongTermSummaries(
  projectId: string,
  ranges: Array<[number, number]>,
): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/chapter-context/summaries/long-term`, {
    data: {
      ranges,
    },
  });
}

export async function fetchLongTermSummariesPage(
  projectId: string,
  page: number,
  pageSize = 20,
  signal?: AbortSignal,
  query?: string,
): Promise<LongTermSummaryListResponse> {
  const response = await apiClient.get<Record<string, unknown>>(
    `/projects/${projectId}/chapter-context/summaries/long-term`,
    { params: { page, page_size: pageSize, ...(query ? { q: query } : {}) }, signal },
  );
  return {
    items: ((response.data.items as Record<string, unknown>[]) || []).map(
      transformLongTermSummaryListItem,
    ),
    total: Number(response.data.total ?? 0),
    page: Number(response.data.page ?? page),
    pageSize: Number(response.data.page_size ?? pageSize),
  };
}

export async function enqueueSummary(
  projectId: string,
  data: EnqueueSummaryRequest,
): Promise<EnqueueSummaryResponse> {
  const response = await apiClient.post<Record<string, unknown>>(
    `/projects/${projectId}/chapter-context/summaries/enqueue`,
    {
      summary_type: data.summaryType,
      chapter_id: data.chapterId,
      start_order: data.startOrder,
      end_order: data.endOrder,
    },
  );
  return {
    summaryId: (response.data.summary_id as string | null) ?? null,
    status: (response.data.status as string) || "queued",
    jobId: (response.data.job_id as string | null) ?? null,
    itemCount: Number(response.data.item_count ?? 0),
  };
}

export async function cancelBackgroundJob(jobId: string, reason: string): Promise<void> {
  await apiClient.post(`/background/jobs/${jobId}/cancel`, { reason });
}

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
