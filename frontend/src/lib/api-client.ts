/**
 * Compatibility facade for legacy feature APIs.
 *
 * New feature APIs should depend on api-transport directly instead of this aggregation module.
 */

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
export {
  fetchAuthPreferences,
  fetchAuthStatus,
  loginWithPassword,
} from "../features/auth/lib/auth-api";
export type {
  AuthLoginRequest,
  AuthPreferencesResponse,
  AuthStatusResponse,
} from "../features/auth/lib/auth-api";
export { checkHealth } from "./health-api";
export type { HealthResponse } from "./health-api";

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
export { fetchModels } from "../features/settings/lib/model-api";
