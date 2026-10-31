import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";

export type ProjectFolderScope =
  | "writing"
  | "discussion"
  | "world"
  | "character"
  | "note"
  | "outline";

export interface ProjectFolder {
  id: string;
  projectId: string;
  scope: ProjectFolderScope;
  title: string;
  description?: string | null;
  order: number;
  createdAt: string;
  updatedAt: string;
}

function transformFolder(raw: schemas.ProjectFolderResponse): ProjectFolder {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    scope: raw.scope as ProjectFolderScope,
    title: raw.title as string,
    description: (raw.description as string | null) ?? null,
    order: raw.order as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchProjectFolders(
  projectId: string,
  scope: ProjectFolderScope,
): Promise<ProjectFolder[]> {
  const response = await http.listProjectFoldersApiV1ProjectsProjectIdFoldersGet(projectId, {
    scope,
  });
  return (response.data.items ?? []).map(transformFolder);
}

export async function createProjectFolder(
  projectId: string,
  scope: ProjectFolderScope,
  title: string,
  description?: string | null,
): Promise<ProjectFolder> {
  const response = await http.createProjectFolderApiV1ProjectsProjectIdFoldersPost(projectId, {
    scope,
    title,
    description,
  });
  return transformFolder(response.data);
}

export async function renameProjectFolder(
  folderId: string,
  title: string,
  description?: string | null,
): Promise<ProjectFolder> {
  const response = await http.updateProjectFolderApiV1FoldersFolderIdPatch(folderId, {
    title,
    description,
  });
  return transformFolder(response.data);
}

export async function deleteProjectFolder(folderId: string): Promise<void> {
  await http.deleteProjectFolderApiV1FoldersFolderIdDelete(folderId);
}

export async function moveProjectFolderItem(
  projectId: string,
  scope: ProjectFolderScope,
  itemId: string,
  folderId: string | null,
): Promise<void> {
  await http.moveProjectFolderItemApiV1ProjectsProjectIdFoldersItemsMovePost(projectId, {
    scope,
    item_id: itemId,
    folder_id: folderId,
  });
}

export async function reorderProjectFolders(
  projectId: string,
  scope: ProjectFolderScope,
  orderedIds: string[],
): Promise<number> {
  const response = await http.reorderProjectFoldersApiV1ProjectsProjectIdFoldersReorderPost(
    projectId,
    {
      scope,
      ordered_ids: orderedIds,
    },
  );
  return response.data.updated_count as number;
}
