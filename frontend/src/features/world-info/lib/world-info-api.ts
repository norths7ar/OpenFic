import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
import { getApiUrl } from "@/lib/api-transport";
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

function transformWorldInfo(raw: schemas.WorldInfoResponse): WorldInfo {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string | null,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformWorldInfoEntry(raw: schemas.WorldInfoEntryResponse): WorldInfoEntry {
  return {
    id: raw.id as string,
    worldInfoId: raw.world_info_id as string,
    folderId: (raw.folder_id as string | null | undefined) ?? null,
    uid: raw.uid as number,
    name: raw.name as string,
    section: (raw.section as string | undefined) ?? "",
    order: raw.order as number,
    content: raw.content as string,
    tokenCount: raw.token_count as number,
    agentVisibility: raw.agent_visibility,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformWorldInfoEntryBrief(
  raw: schemas.WorldInfoEntryBriefResponse,
): WorldInfoEntryBrief {
  return {
    id: raw.id as string,
    worldInfoId: raw.world_info_id as string,
    folderId: (raw.folder_id as string | null | undefined) ?? null,
    uid: raw.uid as number,
    name: raw.name as string,
    section: (raw.section as string | undefined) ?? "",
    order: raw.order as number,
    tokenCount: raw.token_count as number,
    agentVisibility: raw.agent_visibility as string,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformWorldInfoImportPreview(
  raw: schemas.WorldInfoImportPreviewResponse,
): WorldInfoImportPreviewResponse {
  return {
    entryCount: raw.entry_count as number,
    enabledCount: raw.enabled_count as number,
    entries: (raw.entries || []).map((entry) => ({
      uid: entry.uid as number,
      name: entry.name as string,
      section: (entry.section as string | undefined) ?? "",
      contentPreview: (entry.content_preview as string) || "",
      agentVisibility: entry.agent_visibility,
    })),
  };
}

export async function fetchWorldInfoById(worldInfoId: string): Promise<WorldInfo> {
  const response = await http.getWorldInfoApiV1WorldInfoWorldInfoIdGet(worldInfoId);
  return transformWorldInfo(response.data);
}

export async function fetchWorldInfoByProject(projectId: string): Promise<WorldInfo> {
  const response = await http.getProjectWorldInfoApiV1ProjectsProjectIdWorldInfoGet(projectId);
  return transformWorldInfo(response.data);
}

export async function deleteWorldInfo(worldInfoId: string): Promise<void> {
  await http.deleteWorldInfoApiV1WorldInfoWorldInfoIdDelete(worldInfoId);
}

export async function fetchWorldInfoEntries(
  worldInfoId: string,
): Promise<WorldInfoEntryBriefListResponse> {
  const response = await http.listEntriesApiV1WorldInfoWorldInfoIdEntriesGet(worldInfoId);
  const data = response.data;
  return {
    items: data.items.map(transformWorldInfoEntryBrief),
    total: data.total,
  };
}

export async function fetchWorldInfoEntry(entryId: string): Promise<WorldInfoEntry> {
  const response = await http.getEntryApiV1WorldInfoEntriesEntryIdGet(entryId);
  return transformWorldInfoEntry(response.data);
}

export async function createWorldInfoEntry(
  worldInfoId: string,
  data: WorldInfoEntryCreate,
): Promise<WorldInfoEntry> {
  const response = await http.createEntryApiV1WorldInfoWorldInfoIdEntriesPost(worldInfoId, {
    name: data.name,
    content: data.content ?? "",
    token_count: data.tokenCount ?? 0,
    agent_visibility: (data.agentVisibility ?? "all") as schemas.AgentVisibility,
  });
  return transformWorldInfoEntry(response.data);
}

export async function updateWorldInfoEntry(
  entryId: string,
  data: WorldInfoEntryUpdate,
): Promise<WorldInfoEntry> {
  const response = await http.updateEntryApiV1WorldInfoEntriesEntryIdPatch(entryId, {
    name: data.name,
    content: data.content,
    token_count: data.tokenCount,
    agent_visibility: data.agentVisibility as schemas.AgentVisibility | undefined,
  });
  return transformWorldInfoEntry(response.data);
}

export async function deleteWorldInfoEntry(entryId: string): Promise<void> {
  await http.deleteEntryApiV1WorldInfoEntriesEntryIdDelete(entryId);
}

export async function deleteAllWorldInfoEntries(
  worldInfoId: string,
): Promise<{ deletedCount: number }> {
  const response = await http.deleteAllEntriesApiV1WorldInfoWorldInfoIdEntriesDelete(worldInfoId);
  return { deletedCount: response.data.deleted_count };
}

export async function moveWorldInfoEntry(
  entryId: string,
  newOrder: number,
): Promise<WorldInfoEntryBrief> {
  const response = await http.moveEntryApiV1WorldInfoEntriesEntryIdMovePost(entryId, {
    new_order: newOrder,
  });
  return transformWorldInfoEntryBrief(response.data);
}

export async function batchToggleWorldInfoEntries(
  worldInfoId: string,
  entryIds: string[],
  agentVisibility: string,
): Promise<number> {
  const response = await http.batchToggleEntriesApiV1WorldInfoWorldInfoIdEntriesBatchTogglePost(
    worldInfoId,
    {
      entry_ids: entryIds,
      agent_visibility: agentVisibility as schemas.AgentVisibility,
    },
  );
  return response.data.updated_count as number;
}

export async function batchDeleteWorldInfoEntries(
  worldInfoId: string,
  entryIds: string[],
): Promise<number> {
  const response = await http.batchDeleteEntriesApiV1WorldInfoWorldInfoIdEntriesBatchDeletePost(
    worldInfoId,
    {
      entry_ids: entryIds,
    },
  );
  return response.data.deleted_count as number;
}

export async function searchWorldInfoEntries(
  worldInfoId: string,
  query: string,
): Promise<WorldInfoEntrySearchResponse> {
  const response = await http.searchEntriesApiV1WorldInfoWorldInfoIdEntriesSearchGet(worldInfoId, {
    q: query,
  });
  const data = response.data;
  return {
    results: (data.results ?? []).map((result) => ({
      entryId: result.entry_id as string,
      entryName: result.entry_name as string,
      uid: result.uid as number,
      matches: (result.matches ?? []).map((match) => ({
        lineNumber: match.line_number as number,
        lineText: match.line_text as string,
      })),
    })),
    totalEntries: data.total_entries as number,
    totalMatches: data.total_matches as number,
  };
}

export async function previewWorldInfoImport(file: File): Promise<WorldInfoImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await http.previewWorldInfoImportApiV1WorldInfoImportPreviewPost(formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return transformWorldInfoImportPreview(response.data);
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
