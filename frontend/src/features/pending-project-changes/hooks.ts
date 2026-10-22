import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { projectFolderKeys } from "@/features/project-folders/hooks/use-project-folders";
import { invalidateWritingEditorEntityQueries } from "@/features/writing/hooks/use-writing-editor-entity";
import { apiClient } from "@/lib/api-transport";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";

import {
  applyPendingProjectChange,
  countPendingProjectChanges,
  getPendingProjectChange,
  getPendingProjectChangeRevision,
  listPendingProjectChangeRevisions,
  listPendingProjectChanges,
  rejectPendingProjectChange,
  revisePendingProjectChange,
} from "./api";
import type {
  PendingProjectChange,
  PendingProjectChangeApplyRequest,
  PendingProjectChangeStatus,
} from "./types";

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
  detailRoot: (projectId: string) =>
    [PENDING_PROJECT_CHANGES_QUERY_KEY, "detail", projectId] as const,
  detail: (projectId: string, changeId: string | null) =>
    [...pendingProjectChangesQueryKeys.detailRoot(projectId), changeId] as const,
  revisionsRoot: (projectId: string) =>
    [PENDING_PROJECT_CHANGES_QUERY_KEY, "revisions", projectId] as const,
  revisions: (projectId: string, changeId: string | null) =>
    [...pendingProjectChangesQueryKeys.revisionsRoot(projectId), changeId] as const,
  revision: (projectId: string, changeId: string | null, revisionId: string | null) =>
    [...pendingProjectChangesQueryKeys.revisions(projectId, changeId), revisionId] as const,
};

export function usePendingProjectChanges(projectId: string, status?: PendingProjectChangeStatus) {
  const queryClient = useQueryClient();
  useEffect(() => {
    // Canonical editors also save directly through feature APIs (outside useMutation).
    // Observe successful writes while this inbox is mounted, including autosaves.
    const interceptor = apiClient.interceptors.response.use((response) => {
      const method = response.config.method?.toLowerCase();
      const path = response.config.url?.split("?")[0] ?? "";
      const projectPath = path.startsWith(`/projects/${projectId}/`)
        ? path.slice(`/projects/${projectId}`.length)
        : null;
      const canonicalWrite =
        ((method === "patch" || method === "delete") &&
          /^\/(notes|note-categories|folders|characters|world-info-entries)\/[^/]+$/.test(path)) ||
        (method === "patch" && /^\/notes\/[^/]+\/lock$/.test(path)) ||
        (method === "delete" && /^\/world-info\/[^/]+(?:\/entries)?$/.test(path)) ||
        (method === "post" &&
          ((projectPath !== null &&
            /^(\/(notes|note-categories|folders|characters)|\/characters\/batch\/delete|\/folders\/items\/move)$/.test(
              projectPath,
            )) ||
            /^\/world-info\/[^/]+\/entries(?:\/batch\/(toggle|delete))?$/.test(path) ||
            path === "/note-items/move"));
      // Responses with explicit project ownership must belong to this inbox.
      const owner = response.data?.project_id;
      if (canonicalWrite && (!owner || owner === projectId)) {
        void queryClient.invalidateQueries({
          queryKey: pendingProjectChangesQueryKeys.listRoot(projectId),
        });
        void queryClient.invalidateQueries({
          queryKey: pendingProjectChangesQueryKeys.detailRoot(projectId),
        });
      }
      return response;
    });
    return () => apiClient.interceptors.response.eject(interceptor);
  }, [projectId, queryClient]);
  return useQuery({
    queryKey: pendingProjectChangesQueryKeys.list(projectId, status),
    queryFn: () => listPendingProjectChanges(projectId, status),
    enabled: Boolean(projectId),
    staleTime: 0,
  });
}

export function usePendingProjectChange(projectId: string, changeId: string | null) {
  return useQuery({
    queryKey: pendingProjectChangesQueryKeys.detail(projectId, changeId),
    queryFn: () => getPendingProjectChange(projectId, changeId!),
    enabled: Boolean(projectId && changeId),
    staleTime: 0,
  });
}

export function usePendingProjectChangeRevisions(projectId: string, changeId: string | null) {
  return useQuery({
    queryKey: pendingProjectChangesQueryKeys.revisions(projectId, changeId),
    queryFn: () => listPendingProjectChangeRevisions(projectId, changeId!),
    enabled: Boolean(projectId && changeId),
    staleTime: 0,
  });
}

export function usePendingProjectChangeRevision(
  projectId: string,
  changeId: string | null,
  revisionId: string | null,
) {
  return useQuery({
    queryKey: pendingProjectChangesQueryKeys.revision(projectId, changeId, revisionId),
    queryFn: () => getPendingProjectChangeRevision(projectId, changeId!, revisionId!),
    enabled: Boolean(projectId && changeId && revisionId),
    staleTime: Infinity,
  });
}

export function useRefreshPendingProjectChanges(projectId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.listRoot(projectId),
      }),
      queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.countRoot(projectId),
      }),
      queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.detailRoot(projectId),
      }),
      queryClient.invalidateQueries({
        queryKey: pendingProjectChangesQueryKeys.revisionsRoot(projectId),
      }),
    ]);
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
  const refresh = useRefreshPendingProjectChanges(projectId);

  return useMutation({
    mutationFn: (change: PendingProjectChange) =>
      rejectPendingProjectChange(projectId, change.id, change.updated_at),
    onSuccess: (change) => {
      queryClient.setQueryData(pendingProjectChangesQueryKeys.detail(projectId, change.id), change);
      void refresh();
    },
  });
}

export function useApplyPendingProjectChange(projectId: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshPendingProjectChanges(projectId);

  return useMutation({
    mutationFn: ({
      change,
      request,
    }: {
      change: PendingProjectChange;
      request: PendingProjectChangeApplyRequest;
    }) => applyPendingProjectChange(projectId, change.id, request),
    onSuccess: (change, { change: reviewed }) => {
      queryClient.setQueryData(pendingProjectChangesQueryKeys.detail(projectId, change.id), change);
      void refresh();
      if (["note", "outline", "note_category"].includes(change.target_type)) {
        void queryClient.invalidateQueries({
          queryKey: projectDataQueryKeys.notes.projectTrees(projectId),
        });
        if (change.target_type === "note_category") {
          void queryClient.invalidateQueries({
            queryKey: projectFolderKeys.list(projectId, "note"),
          });
          void queryClient.invalidateQueries({
            queryKey: projectFolderKeys.list(projectId, "outline"),
          });
        } else if (change.target_id) {
          void queryClient.invalidateQueries({
            queryKey: projectDataQueryKeys.notes.detail(change.target_id),
          });
        }
      }
      if (change.target_type === "character") {
        void queryClient.invalidateQueries({
          queryKey: projectDataQueryKeys.characters.list(projectId),
        });
        void queryClient.invalidateQueries({ queryKey: ["characters-search", projectId] });
        if (change.target_id) {
          void queryClient.invalidateQueries({
            queryKey: projectDataQueryKeys.characters.detail(change.target_id),
          });
        }
      }
      if (change.target_type === "world_entry") {
        const snapshot = change.current ?? reviewed.current;
        const worldInfoId =
          snapshot &&
          typeof snapshot === "object" &&
          !Array.isArray(snapshot) &&
          typeof snapshot.world_info_id === "string"
            ? snapshot.world_info_id
            : queryClient.getQueryData<{ id: string }>(
                projectDataQueryKeys.worldInfo.byProject(projectId),
              )?.id;
        void queryClient.invalidateQueries({
          queryKey: projectDataQueryKeys.worldInfo.byProject(projectId),
        });
        if (worldInfoId) {
          void queryClient.invalidateQueries({
            queryKey: projectDataQueryKeys.worldInfo.entries(worldInfoId),
          });
          void queryClient.invalidateQueries({
            queryKey: ["world-info-entries-search", worldInfoId],
          });
        }
        if (change.target_id) {
          void queryClient.invalidateQueries({
            queryKey: projectDataQueryKeys.worldInfo.entryDetail(change.target_id),
          });
        }
      }
      if (change.target_type === "chapter") {
        invalidateWritingEditorEntityQueries(queryClient, "chapter", change.target_id ?? undefined);
      }
      if (change.target_type === "note" || change.target_type === "outline") {
        invalidateWritingEditorEntityQueries(queryClient, "note", change.target_id ?? undefined);
      }
    },
  });
}

export function useRevisePendingProjectChange(projectId: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshPendingProjectChanges(projectId);
  return useMutation({
    mutationFn: ({
      change,
      patch,
    }: {
      change: PendingProjectChange;
      patch: Record<string, string>;
    }) => revisePendingProjectChange(projectId, change.id, change.updated_at, patch),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        pendingProjectChangesQueryKeys.detail(projectId, updated.id),
        updated,
      );
      queryClient.setQueriesData<PendingProjectChange[]>(
        { queryKey: pendingProjectChangesQueryKeys.listRoot(projectId) },
        (items) => items?.map((item) => (item.id === updated.id ? updated : item)),
      );
      void refresh();
    },
  });
}
