import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { projectDataQueryKeys } from "@/lib/project-data-query-keys";

import {
  createProjectFolder,
  deleteProjectFolder,
  fetchProjectFolders,
  moveProjectFolderItem,
  renameProjectFolder,
  reorderProjectFolders,
  type ProjectFolderScope,
} from "../lib/project-folder-api";

export const projectFolderKeys = {
  list: (projectId: string, scope: ProjectFolderScope) =>
    ["project-folders", projectId, scope] as const,
};

export function useProjectFolders(projectId: string | null, scope: ProjectFolderScope) {
  return useQuery({
    queryKey: projectFolderKeys.list(projectId ?? "", scope),
    queryFn: () => fetchProjectFolders(projectId!, scope),
    enabled: Boolean(projectId),
  });
}

export function useProjectFolderMutations(projectId: string, scope: ProjectFolderScope) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: projectFolderKeys.list(projectId, scope) });
  const invalidateItems = () => {
    if (scope === "note" || scope === "outline") {
      return queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.notes.projectTrees(projectId),
      });
    }
    if (scope === "writing") {
      return queryClient.invalidateQueries({ queryKey: ["volume-tree", projectId] });
    }
    if (scope === "character") {
      return queryClient.invalidateQueries({ queryKey: projectDataQueryKeys.characters.lists });
    }
    if (scope === "world") {
      return queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.worldInfo.entriesLists,
      });
    }
    return queryClient.invalidateQueries({ queryKey: ["tasks", projectId], exact: false });
  };

  return {
    create: useMutation({
      mutationFn: (value: string | { title: string; description?: string | null }) =>
        createProjectFolder(
          projectId,
          scope,
          typeof value === "string" ? value : value.title,
          typeof value === "string" ? undefined : value.description,
        ),
      onSuccess: invalidate,
    }),
    rename: useMutation({
      mutationFn: ({
        folderId,
        title,
        description,
      }: {
        folderId: string;
        title: string;
        description?: string | null;
      }) => renameProjectFolder(folderId, title, description),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: deleteProjectFolder,
      onSuccess: () => Promise.all([invalidate(), invalidateItems()]),
    }),
    moveItem: useMutation({
      mutationFn: ({ itemId, folderId }: { itemId: string; folderId: string | null }) =>
        moveProjectFolderItem(projectId, scope, itemId, folderId),
      onSuccess: invalidateItems,
    }),
    reorder: useMutation({
      mutationFn: (orderedIds: string[]) => reorderProjectFolders(projectId, scope, orderedIds),
      onSuccess: invalidate,
    }),
  };
}
