import { apiClient, resolveBackendUrl } from "@/lib/api-transport";
import type {
  Project,
  ProjectCreate,
  ProjectListParams,
  ProjectListResponse,
  ProjectUpdate,
} from "@/lib/project.types";

function transformProject(raw: Record<string, unknown>): Project {
  return {
    id: raw.id as string,
    title: raw.title as string,
    description: raw.description as string | null,
    wordCount: raw.word_count as number,
    chapterCount: raw.chapter_count as number,
    coverUrl: resolveBackendUrl(raw.cover_url as string | null | undefined),
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchProjects(params?: ProjectListParams): Promise<ProjectListResponse> {
  const response = await apiClient.get("/projects", {
    params: {
      page: params?.page ?? 1,
      page_size: params?.pageSize ?? 20,
      search: params?.search?.trim() || undefined,
      sort_by: params?.sortBy ?? "updated_at",
      sort_order: params?.sortOrder ?? "desc",
    },
  });
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map(transformProject),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function fetchProject(projectId: string): Promise<Project> {
  const response = await apiClient.get(`/projects/${projectId}`);
  return transformProject(response.data);
}

export async function createProject(data: ProjectCreate): Promise<Project> {
  const formData = new FormData();
  formData.append("title", data.title);
  if (data.description) formData.append("description", data.description);
  if (data.cover) formData.append("cover", data.cover);

  const response = await apiClient.post("/projects", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return transformProject(response.data);
}

export async function updateProject(projectId: string, data: ProjectUpdate): Promise<Project> {
  const formData = new FormData();
  if (data.title !== undefined) formData.append("title", data.title || "");
  if (data.description !== undefined) formData.append("description", data.description || "");
  if (data.cover) formData.append("cover", data.cover);

  const response = await apiClient.patch(`/projects/${projectId}`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return transformProject(response.data);
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiClient.delete(`/projects/${projectId}`);
}
