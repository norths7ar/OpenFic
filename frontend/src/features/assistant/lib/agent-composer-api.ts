import { apiClient } from "@/lib/api-transport";
import type { AssistantCommandCandidate } from "@/lib/command.types";
import type { AssistantMentionCandidate } from "@/lib/mention.types";

function transformMentionCandidate(raw: Record<string, unknown>): AssistantMentionCandidate {
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

function transformCommandCandidate(raw: Record<string, unknown>): AssistantCommandCandidate {
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
): Promise<AssistantMentionCandidate[]> {
  const response = await apiClient.get<Record<string, unknown>>(`/projects/${projectId}/mentions`, {
    params: {
      query,
      limit,
      ...(kind ? { kind } : {}),
    },
    signal,
  });
  return ((response.data.items as Record<string, unknown>[]) ?? []).map(transformMentionCandidate);
}

export async function searchCommands(
  projectId: string,
  query: string,
  limit = 20,
  kind: "skill" = "skill",
  signal?: AbortSignal,
): Promise<AssistantCommandCandidate[]> {
  const response = await apiClient.get<Record<string, unknown>>(`/projects/${projectId}/commands`, {
    params: { query, limit, kind },
    signal,
  });
  return ((response.data.items as Record<string, unknown>[]) ?? []).map(transformCommandCandidate);
}
