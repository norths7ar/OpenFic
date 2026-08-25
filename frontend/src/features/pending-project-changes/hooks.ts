import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.listRoot(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.countRoot(projectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["note-tree", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["note"] });
      void queryClient.invalidateQueries({ queryKey: ["characters", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["character"] });
      void queryClient.invalidateQueries({ queryKey: ["world-info-by-project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["world-info-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["world-info-entry-detail"] });
    },
  });
}
