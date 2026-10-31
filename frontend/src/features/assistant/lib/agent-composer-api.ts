import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
import type { AssistantCommandCandidate } from "@/lib/command.types";
import type {
  AssistantMentionCandidate,
  AssistantMentionSearchResponse,
} from "@/lib/mention.types";

function transformMentionCandidate(raw: schemas.MentionCandidateItem): AssistantMentionCandidate {
  return {
    kind: raw.kind as
      | "volume"
      | "chapter"
      | "note"
      | "note_category"
      | "world_info_entry"
      | "character",
    id: raw.id as string,
    title: raw.title as string,
    label: raw.label as string,
    description: typeof raw.description === "string" ? raw.description : undefined,
  };
}

function transformCommandCandidate(raw: schemas.CommandCandidateItem): AssistantCommandCandidate {
  return {
    kind: "skill",
    id: raw.id as string,
    name: raw.name as string,
    description: raw.description as string,
  };
}

export async function searchMentionCandidates(
  projectId: string,
  query: string,
  limit = 20,
  kind?: "volume" | "chapter" | "note" | "note_category" | "world_info_entry" | "character",
  signal?: AbortSignal,
  options: { contextMode?: "global" | "local"; folderId?: string; offset?: number } = {},
): Promise<AssistantMentionSearchResponse> {
  const response = await http.searchMentionCandidatesApiV1ProjectsProjectIdMentionsGet(
    projectId,
    {
      query,
      limit,
      ...(kind ? { kind } : {}),
      context_mode: options.contextMode ?? "local",
      ...(options.folderId !== undefined ? { folder_id: options.folderId } : {}),
      offset: options.offset ?? 0,
    },
    { signal },
  );
  return {
    items: (response.data.items ?? []).map(transformMentionCandidate),
    folders: (response.data.folders as { id: string; title: string }[]) ?? [],
    hasMore: response.data.has_more === true,
  };
}

export async function searchCommands(
  projectId: string,
  query: string,
  limit = 20,
  kind: "skill" = "skill",
  signal?: AbortSignal,
): Promise<AssistantCommandCandidate[]> {
  const response = await http.searchCommandsApiV1ProjectsProjectIdCommandsGet(
    projectId,
    { query, limit, kind },
    { signal },
  );
  return (response.data.items ?? []).map(transformCommandCandidate);
}
