import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { invalidateWritingEditorEntityQueries } from "@/features/writing/hooks/use-writing-editor-entity";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";

import {
  applyPendingProjectChange,
  countPendingProjectChanges,
  listPendingProjectChanges,
  rejectPendingProjectChange,
} from "./api";
import type { PendingProjectChangeStatus } from "./types";

const PENDING_PROJECT_CHANGES_QUERY_KEY = "pending-project-changes";

export const pendingProjectChangesQueryKeys = {
  all: [PENDING_PROJECT_CHANGES_QUERY_KEY] as const,
  listRoot: (projectId: string) => [PENDING_PROJECT_CHANGES_QUERY_KEY, "list", projectId] as const,
  list: (projectId: string, status?: PendingProjectChangeStatus) =>
    [...pendingProjectChangesQueryKeys.listRoot(projectId), status ?? "all"] as const,
  countRoot: (projectId: string) =>
    [PENDING_PROJECT_CHANGES_QUERY_KEY, "count", projectId] as const,
  count: (projectId: string, status: PendingProjectChangeStatus = "pending") =>
    [...pendingProjectChangesQueryKeys.countRoot(projectId), status] as const,
};

export function usePendingProjectChanges(projectId: string, status?: PendingProjectChangeStatus) {
  return useQuery({
    queryKey: pendingProjectChangesQueryKeys.list(projectId, status),
    queryFn: () => listPendingProjectChanges(projectId, status),
    enabled: Boolean(projectId),
  });
}

export function usePendingProjectChangeCount(
  projectId: string,
  status: PendingProjectChangeStatus = "pending",
) {
  return useQuery({
    queryKey: pendingProjectChangesQueryKeys.count(projectId, status),
    queryFn: () => countPendingProjectChanges(projectId, status),
    enabled: Boolean(projectId),
  });
}

export function useRejectPendingProjectChange(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (changeId: string) => rejectPendingProjectChange(projectId, changeId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.listRoot(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.countRoot(projectId),
      });
    },
  });
}

export function useApplyPendingProjectChange(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (changeId: string) => applyPendingProjectChange(projectId, changeId),
    onSuccess: (change) => {
      void queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.listRoot(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.countRoot(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.notes.projectTrees(projectId),
      });
      void queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.notes.details });
      void queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(projectId),
      });
      void queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.characters.details });
      void queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.worldInfo.byProject(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.worldInfo.entriesLists,
      });
      void queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.worldInfo.entryDetails,
      });
      if (change.target_type === "chapter") {
        invalidateWritingEditorEntityQueries(queryClient, "chapter", change.target_id ?? undefined);
      }
      if (change.target_type === "note" || change.target_type === "outline") {
        invalidateWritingEditorEntityQueries(queryClient, "note", change.target_id ?? undefined);
      }
    },
  });
}
