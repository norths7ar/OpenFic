import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
import type {
  CompileResponse,
  CreateVersionRequest,
  PromptCategoryMetadata,
  PromptChainVersion,
  PromptChainsMetadata,
  PromptEntry,
  PromptEntrySearchResponse,
  VersionDiff,
  VersionWithEntries,
} from "@/lib/prompt-chain.types";

function normalizeUtcDateString(value: unknown): string {
  if (typeof value !== "string") return "";

  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  if (hasTimezone) return value;

  return `${value}Z`;
}

function transformPromptChainVersion(raw: schemas.PromptChainVersionResponse): PromptChainVersion {
  return {
    id: raw.id as string,
    promptId: raw.prompt_id as string,
    versionHash: raw.version_hash as string,
    versionNumber: raw.version_number as number,
    parentVersionId: raw.parent_version_id as string | null,
    isActive: raw.is_active as boolean,
    note: raw.note as string | null,
    createdAt: normalizeUtcDateString(raw.created_at),
  };
}

function transformPromptEntry(raw: schemas.PromptEntryResponse): PromptEntry {
  return {
    id: raw.id as string,
    uid: raw.uid as string,
    versionId: raw.version_id as string,
    name: raw.name as string,
    role: raw.role as "system" | "user" | "assistant",
    content: raw.content as string,
    orderIndex: raw.order_index as number,
    isEnabled: raw.is_enabled as boolean,
    tokenCount: raw.token_count as number,
    createdAt: normalizeUtcDateString(raw.created_at),
    updatedAt: normalizeUtcDateString(raw.updated_at),
  };
}

export async function fetchPromptChainVersions(
  promptId: string,
  activeOnly: boolean = false,
): Promise<PromptChainVersion[]> {
  const response = await http.listVersionsApiV1PromptChainsPromptIdVersionsGet(promptId, {
    active_only: activeOnly,
  });
  return response.data.map(transformPromptChainVersion);
}

export async function fetchLatestPromptChainVersion(promptId: string): Promise<VersionWithEntries> {
  const response = await http.getLatestVersionApiV1PromptChainsPromptIdVersionsLatestGet(promptId);
  return {
    version: transformPromptChainVersion(response.data.version),
    entries: response.data.entries.map(transformPromptEntry),
  };
}

export async function fetchPromptChainVersion(
  promptId: string,
  versionId: string,
): Promise<VersionWithEntries> {
  const response = await http.getVersionApiV1PromptChainsPromptIdVersionsVersionIdGet(
    promptId,
    versionId,
  );
  return {
    version: transformPromptChainVersion(response.data.version),
    entries: response.data.entries.map(transformPromptEntry),
  };
}

export async function searchPromptChainVersionEntries(
  promptId: string,
  versionId: string,
  query: string,
): Promise<PromptEntrySearchResponse> {
  const response =
    await http.searchVersionEntriesApiV1PromptChainsPromptIdVersionsVersionIdSearchGet(
      promptId,
      versionId,
      { q: query },
    );
  return {
    results: (response.data.results ?? []).map((result) => ({
      entryId: result.entry_id as string,
      entryName: result.entry_name as string,
      role: result.role as "system" | "user" | "assistant",
      matches: result.matches.map((match) => ({
        lineNumber: match.line_number as number,
        lineText: match.line_text as string,
      })),
    })),
    totalEntries: response.data.total_entries as number,
    totalMatches: response.data.total_matches as number,
  };
}

export async function createPromptChainVersion(
  promptId: string,
  request: CreateVersionRequest,
): Promise<VersionWithEntries> {
  const requestData = {
    parent_version_id: request.parentVersionId,
    entries: request.entries,
    note: request.note,
  };

  const response = await http.createVersionApiV1PromptChainsPromptIdVersionsPost(
    promptId,
    requestData,
  );
  return {
    version: transformPromptChainVersion(response.data.version),
    entries: response.data.entries.map(transformPromptEntry),
  };
}

export async function compilePromptChain(promptId: string): Promise<CompileResponse> {
  const response = await http.compilePromptChainApiV1PromptChainsPromptIdCompilePost(promptId);
  return response.data;
}

export async function fetchPromptChainsMetadata(): Promise<PromptChainsMetadata> {
  const response = await http.getCategoriesApiV1PromptChainsCategoriesGet();
  if (!isPromptChainsMetadata(response.data)) {
    throw new Error("提示词分类响应格式无效");
  }
  return response.data;
}

function isPromptChainsMetadata(value: unknown): value is PromptChainsMetadata {
  if (!value || typeof value !== "object") return false;
  const categories = (value as { categories?: unknown }).categories;
  return Array.isArray(categories) && categories.every(isPromptCategoryMetadata);
}

function isPromptCategoryMetadata(value: unknown): value is PromptCategoryMetadata {
  if (!value || typeof value !== "object") return false;
  const category = value as { id?: unknown; label_key?: unknown; prompts?: unknown };
  return (
    typeof category.id === "string" &&
    typeof category.label_key === "string" &&
    Array.isArray(category.prompts) &&
    category.prompts.every(isPromptMetadata)
  );
}

function isPromptMetadata(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const prompt = value as {
    id?: unknown;
    label_key?: unknown;
    label?: unknown;
    visibility?: unknown;
    editable?: unknown;
  };
  return (
    typeof prompt.id === "string" &&
    typeof prompt.label_key === "string" &&
    (typeof prompt.label === "string" || prompt.label === null) &&
    (prompt.visibility === "user" ||
      prompt.visibility === "advanced" ||
      prompt.visibility === "internal") &&
    typeof prompt.editable === "boolean"
  );
}

export async function fetchVersionDiff(
  promptId: string,
  baseVersionId: string,
  compareVersionId: string,
): Promise<VersionDiff> {
  const response =
    await http.diffVersionsApiV1PromptChainsPromptIdVersionsVersionIdDiffCompareVersionIdGet(
      promptId,
      baseVersionId,
      compareVersionId,
    );

  return {
    baseVersion: transformPromptChainVersion(response.data.base_version),
    compareVersion: transformPromptChainVersion(response.data.compare_version),
    diffs: response.data.diffs.map((diff) => ({
      entryId: diff.entry_id as string,
      changeType: diff.change_type as "added" | "deleted" | "modified",
      baseEntry: diff.base_entry ? transformPromptEntry(diff.base_entry) : null,
      compareEntry: diff.compare_entry ? transformPromptEntry(diff.compare_entry) : null,
    })),
  };
}

export async function resetPromptChain(promptId: string): Promise<VersionWithEntries> {
  const response = await http.resetToDefaultApiV1PromptChainsPromptIdResetPost(promptId);

  return {
    version: transformPromptChainVersion(response.data.version),
    entries: response.data.entries.map(transformPromptEntry),
  };
}
