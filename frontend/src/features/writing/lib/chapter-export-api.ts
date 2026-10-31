import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
import { resolveBackendUrl } from "@/lib/api-transport";
import type { ChapterExport, ChapterExportCreate } from "@/lib/chapter-export.types";

function transformChapterExport(raw: schemas.ChapterExportResponse): ChapterExport {
  return {
    id: raw.id as string,
    status: raw.status as string,
    filename: raw.filename as string,
    mode: raw.mode as ChapterExport["mode"],
    volumeCount: Number(raw.volume_count ?? 0),
    chapterCount: Number(raw.chapter_count ?? 0),
    wordCount: Number(raw.word_count ?? 0),
    chapterIds: Array.isArray(raw.chapter_ids)
      ? raw.chapter_ids.filter((chapterId): chapterId is string => typeof chapterId === "string")
      : [],
    current: Number(raw.current ?? 0),
    total: Number(raw.total ?? 0),
    stage: typeof raw.stage === "string" ? raw.stage : null,
    chapterTitle: typeof raw.chapter_title === "string" ? raw.chapter_title : null,
    expiresAt: typeof raw.expires_at === "string" ? raw.expires_at : null,
    downloadUrl: resolveBackendUrl(raw.download_url as string | null | undefined),
    errorMessage: typeof raw.error_message === "string" ? raw.error_message : null,
  };
}

export async function createChapterExport(
  projectId: string,
  data: ChapterExportCreate,
): Promise<ChapterExport> {
  const response = await http.createChapterExportApiV1ProjectsProjectIdChapterExportsPost(
    projectId,
    {
      selected_volume_ids: data.selectedVolumeIds,
      included_chapter_ids: data.includedChapterIds,
      excluded_chapter_ids: data.excludedChapterIds,
      local_date: data.localDate,
    },
  );
  return transformChapterExport(response.data);
}

export async function fetchChapterExport(projectId: string, jobId: string): Promise<ChapterExport> {
  const response = await http.getChapterExportApiV1ProjectsProjectIdChapterExportsJobIdGet(
    projectId,
    jobId,
  );
  return transformChapterExport(response.data);
}

export async function cancelChapterExport(
  projectId: string,
  jobId: string,
): Promise<ChapterExport> {
  const response =
    await http.cancelChapterExportApiV1ProjectsProjectIdChapterExportsJobIdCancelPost(
      projectId,
      jobId,
    );
  return transformChapterExport(response.data);
}
