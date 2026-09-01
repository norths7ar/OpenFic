import { apiClient, getApiUrl } from "@/lib/api-transport";
import { handleAuthenticationFailure } from "@/lib/auth-failure";
import type {
  WorldInfo,
  WorldInfoEntry,
  WorldInfoEntryBrief,
  WorldInfoEntryBriefListResponse,
  WorldInfoEntryCreate,
  WorldInfoEntrySearchResponse,
  WorldInfoEntryUpdate,
  WorldInfoImportCompleteEvent,
  WorldInfoImportEvent,
  WorldInfoImportMode,
  WorldInfoImportPreviewResponse,
} from "@/lib/world-info.types";

function transformWorldInfo(raw: Record<string, unknown>): WorldInfo {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string | null,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformWorldInfoEntry(raw: Record<string, unknown>): WorldInfoEntry {
  return {
    id: raw.id as string,
    worldInfoId: raw.world_info_id as string,
    uid: raw.uid as number,
    name: raw.name as string,
    section: (raw.section as string | undefined) ?? "",
    order: raw.order as number,
    content: raw.content as string,
    tokenCount: raw.token_count as number,
    isEnabled: raw.is_enabled as boolean,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformWorldInfoEntryBrief(raw: Record<string, unknown>): WorldInfoEntryBrief {
  return {
    id: raw.id as string,
    worldInfoId: raw.world_info_id as string,
    uid: raw.uid as number,
    name: raw.name as string,
    section: (raw.section as string | undefined) ?? "",
    order: raw.order as number,
    tokenCount: raw.token_count as number,
    isEnabled: raw.is_enabled as boolean,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformWorldInfoImportPreview(
  raw: Record<string, unknown>,
): WorldInfoImportPreviewResponse {
  return {
    entryCount: raw.entry_count as number,
    enabledCount: raw.enabled_count as number,
    entries: ((raw.entries as Record<string, unknown>[]) || []).map((entry) => ({
      uid: entry.uid as number,
      name: entry.name as string,
      section: (entry.section as string | undefined) ?? "",
      contentPreview: (entry.content_preview as string) || "",
      isEnabled: Boolean(entry.is_enabled),
    })),
  };
}

export async function fetchWorldInfoById(worldInfoId: string): Promise<WorldInfo> {
  const response = await apiClient.get(`/world-info/${worldInfoId}`);
  return transformWorldInfo(response.data);
}

export async function fetchWorldInfoByProject(projectId: string): Promise<WorldInfo> {
  const response = await apiClient.get(`/projects/${projectId}/world-info`);
  return transformWorldInfo(response.data);
}

export async function deleteWorldInfo(worldInfoId: string): Promise<void> {
  await apiClient.delete(`/world-info/${worldInfoId}`);
}

export async function fetchWorldInfoEntries(
  worldInfoId: string,
): Promise<WorldInfoEntryBriefListResponse> {
  const response = await apiClient.get(`/world-info/${worldInfoId}/entries`);
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map(transformWorldInfoEntryBrief),
    total: data.total,
  };
}

export async function fetchWorldInfoEntry(entryId: string): Promise<WorldInfoEntry> {
  const response = await apiClient.get(`/world-info-entries/${entryId}`);
  return transformWorldInfoEntry(response.data);
}

export async function createWorldInfoEntry(
  worldInfoId: string,
  data: WorldInfoEntryCreate,
): Promise<WorldInfoEntry> {
  const response = await apiClient.post(`/world-info/${worldInfoId}/entries`, {
    name: data.name,
    content: data.content ?? "",
    token_count: data.tokenCount ?? 0,
    is_enabled: data.isEnabled ?? true,
  });
  return transformWorldInfoEntry(response.data);
}

export async function updateWorldInfoEntry(
  entryId: string,
  data: WorldInfoEntryUpdate,
): Promise<WorldInfoEntry> {
  const response = await apiClient.patch(`/world-info-entries/${entryId}`, {
    name: data.name,
    content: data.content,
    token_count: data.tokenCount,
    is_enabled: data.isEnabled,
  });
  return transformWorldInfoEntry(response.data);
}

export async function deleteWorldInfoEntry(entryId: string): Promise<void> {
  await apiClient.delete(`/world-info-entries/${entryId}`);
}

export async function deleteAllWorldInfoEntries(
  worldInfoId: string,
): Promise<{ deletedCount: number }> {
  const response = await apiClient.delete(`/world-info/${worldInfoId}/entries`);
  return { deletedCount: response.data.deleted_count };
}

export async function moveWorldInfoEntry(
  entryId: string,
  newOrder: number,
): Promise<WorldInfoEntryBrief> {
  const response = await apiClient.post(`/world-info-entries/${entryId}/move`, {
    new_order: newOrder,
  });
  return transformWorldInfoEntryBrief(response.data);
}

export async function toggleWorldInfoEntry(entryId: string): Promise<WorldInfoEntry> {
  const response = await apiClient.post(`/world-info-entries/${entryId}/toggle`);
  return transformWorldInfoEntry(response.data);
}

export async function batchToggleWorldInfoEntries(
  worldInfoId: string,
  entryIds: string[],
  isEnabled: boolean,
): Promise<number> {
  const response = await apiClient.post(`/world-info/${worldInfoId}/entries/batch/toggle`, {
    entry_ids: entryIds,
    is_enabled: isEnabled,
  });
  return response.data.updated_count as number;
}

export async function batchDeleteWorldInfoEntries(
  worldInfoId: string,
  entryIds: string[],
): Promise<number> {
  const response = await apiClient.post(`/world-info/${worldInfoId}/entries/batch/delete`, {
    entry_ids: entryIds,
  });
  return response.data.deleted_count as number;
}

export async function searchWorldInfoEntries(
  worldInfoId: string,
  query: string,
): Promise<WorldInfoEntrySearchResponse> {
  const response = await apiClient.get(`/world-info/${worldInfoId}/entries/search`, {
    params: { q: query },
  });
  const data = response.data as Record<string, unknown>;
  return {
    results: ((data.results as Record<string, unknown>[]) ?? []).map(
      (result: Record<string, unknown>) => ({
        entryId: result.entry_id as string,
        entryName: result.entry_name as string,
        uid: result.uid as number,
        matches: ((result.matches as Record<string, unknown>[]) ?? []).map(
          (match: Record<string, unknown>) => ({
            lineNumber: match.line_number as number,
            lineText: match.line_text as string,
          }),
        ),
      }),
    ),
    totalEntries: data.total_entries as number,
    totalMatches: data.total_matches as number,
  };
}

export async function previewWorldInfoImport(file: File): Promise<WorldInfoImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post("/world-info/import/preview", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return transformWorldInfoImportPreview(response.data as Record<string, unknown>);
}

export async function importWorldInfoEntriesStream(
  worldInfoId: string,
  file: File,
  mode: WorldInfoImportMode,
  onEvent: (event: WorldInfoImportEvent) => void,
): Promise<WorldInfoImportCompleteEvent | null> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    getApiUrl(`/world-info/${worldInfoId}/entries/import-stream?mode=${mode}`),
    {
      method: "POST",
      body: formData,
      credentials: "include",
    },
  );

  if (!response.ok) {
    if (response.status === 401) handleAuthenticationFailure();
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("无法获取响应流");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let result: WorldInfoImportCompleteEvent | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) {
        continue;
      }

      try {
        const event = JSON.parse(line.slice(6)) as WorldInfoImportEvent;
        onEvent(event);

        if (event.type === "complete") {
          result = event;
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      } catch (error) {
        if (error instanceof SyntaxError) {
          console.warn("无法解析 SSE 事件:", line);
        } else {
          throw error;
        }
      }
    }
  }

  return result;
}
