import {
  projectNavGroups,
  PROJECT_NAV_ROOT_ID,
} from "@/features/project-navigation/lib/project-nav-groups";
import { apiClient } from "@/lib/api-transport";
import type {
  Chapter,
  ChapterCreate,
  ChapterListItem,
  ChapterMoveToVolume,
  ChapterUpdate,
  Volume,
  VolumeCreate,
  VolumeMove,
  VolumeTreeResponse,
  VolumeUpdate,
  VolumeWithChapters,
} from "@/lib/chapter.types";

function transformChapter(raw: Record<string, unknown>): Chapter {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    volumeId: (raw.volume_id as string | null) ?? PROJECT_NAV_ROOT_ID,
    title: raw.title as string,
    content: raw.content as string,
    wordCount: raw.word_count as number,
    order: raw.order as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformChapterListItem(raw: Record<string, unknown>): ChapterListItem {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    volumeId: (raw.volume_id as string | null) ?? PROJECT_NAV_ROOT_ID,
    title: raw.title as string,
    wordCount: raw.word_count as number,
    order: raw.order as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformVolume(raw: Record<string, unknown>): Volume {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    title: raw.title as string,
    description: (raw.description as string | null | undefined) ?? null,
    order: raw.order as number,
    chapterCount: raw.chapter_count as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformVolumeWithChapters(raw: Record<string, unknown>): VolumeWithChapters {
  return {
    ...transformVolume(raw),
    chapters: ((raw.chapters as Record<string, unknown>[]) ?? []).map(transformChapterListItem),
  };
}

function transformVolumeTree(raw: Record<string, unknown>): VolumeTreeResponse {
  const folders = ((raw.volumes as Record<string, unknown>[]) ?? []).map(
    transformVolumeWithChapters,
  );
  const roots = ((raw.root_chapters as Record<string, unknown>[]) ?? []).map(
    transformChapterListItem,
  );
  const items = [...roots, ...folders.flatMap((folder) => folder.chapters)];
  return {
    volumes: projectNavGroups(folders, items, (item) =>
      item.volumeId === PROJECT_NAV_ROOT_ID ? null : item.volumeId,
    ).map(
      (group) =>
        group.folder ?? {
          id: PROJECT_NAV_ROOT_ID,
          projectId: roots[0]?.projectId ?? "",
          title: "",
          description: null,
          order: -1,
          chapterCount: roots.length,
          createdAt: "",
          updatedAt: "",
          chapters: roots,
          isRoot: true,
        },
    ),
    totalChapters: raw.total_chapters as number,
  };
}

export async function fetchChapters(projectId: string): Promise<VolumeTreeResponse> {
  const response = await apiClient.get(`/projects/${projectId}/chapters`);
  return transformVolumeTree(response.data);
}

export async function fetchChapter(chapterId: string): Promise<Chapter> {
  const response = await apiClient.get(`/chapters/${chapterId}`);
  return transformChapter(response.data);
}

export async function createChapter(projectId: string, data: ChapterCreate): Promise<Chapter> {
  const response = await apiClient.post(`/projects/${projectId}/chapters`, {
    volume_id: data.volumeId === PROJECT_NAV_ROOT_ID ? null : data.volumeId,
    title: data.title,
    content: data.content ?? "",
    word_count: data.wordCount,
  });
  return transformChapter(response.data);
}

export async function createVolume(projectId: string, data: VolumeCreate): Promise<Volume> {
  const response = await apiClient.post(`/projects/${projectId}/volumes`, {
    title: data.title,
    description: data.description ?? null,
  });
  return transformVolume(response.data);
}

export async function fetchVolumes(projectId: string): Promise<Volume[]> {
  const response = await apiClient.get(`/projects/${projectId}/volumes`);
  return (response.data as Record<string, unknown>[]).map(transformVolume);
}

export async function fetchVolume(volumeId: string): Promise<Volume> {
  const response = await apiClient.get(`/volumes/${volumeId}`);
  return transformVolume(response.data);
}

export async function updateVolume(volumeId: string, data: VolumeUpdate): Promise<Volume> {
  const response = await apiClient.patch(`/volumes/${volumeId}`, {
    title: data.title,
    description: data.description,
  });
  return transformVolume(response.data);
}

export async function deleteVolume(volumeId: string, cascade = false): Promise<void> {
  await apiClient.delete(`/volumes/${volumeId}`, {
    params: { cascade },
  });
}

export async function moveVolume(volumeId: string, data: VolumeMove): Promise<Volume> {
  const response = await apiClient.post(`/volumes/${volumeId}/move`, {
    new_order: data.newOrder,
  });
  return transformVolume(response.data);
}

export async function updateChapter(chapterId: string, data: ChapterUpdate): Promise<Chapter> {
  const contentBase =
    data.baseTitle !== undefined && data.baseContent !== undefined
      ? { base_title: data.baseTitle, base_content: data.baseContent }
      : {};
  const response = await apiClient.patch(`/chapters/${chapterId}`, {
    title: data.title,
    content: data.content,
    word_count: data.wordCount,
    base_updated_at: data.baseUpdatedAt,
    ...contentBase,
  });
  return transformChapter(response.data);
}

export async function deleteChapter(chapterId: string): Promise<void> {
  await apiClient.delete(`/chapters/${chapterId}`);
}

export async function reorderChapters(
  volumeId: string,
  chapterIds: string[],
): Promise<ChapterListItem[]> {
  const response = await apiClient.post("/chapters/reorder", {
    volume_id: volumeId === PROJECT_NAV_ROOT_ID ? null : volumeId,
    chapter_ids: chapterIds,
  });
  return (response.data as Record<string, unknown>[]).map(transformChapterListItem);
}

export async function moveChapterToVolume(
  chapterId: string,
  data: ChapterMoveToVolume,
): Promise<Chapter> {
  const response = await apiClient.post(`/chapters/${chapterId}/move-to-volume`, {
    volume_id: data.volumeId === PROJECT_NAV_ROOT_ID ? null : data.volumeId,
  });
  return transformChapter(response.data);
}
