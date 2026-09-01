import { apiClient } from "@/lib/api-transport";

export type SummaryStatus = "not_generated" | "queued" | "running" | "ready" | "failed";

export interface LongTermSummaryListItem {
  startOrder: number;
  endOrder: number;
  startVolumeTitle: string | null;
  startChapterTitle: string;
  endVolumeTitle: string | null;
  endChapterTitle: string;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  startTime: string;
  endTime: string;
  summary: string;
  errorMessage: string | null;
  updatedAt: string | null;
}
export interface SummaryStatusItem {
  chapterId: string;
  volumeId: string | null;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  updatedAt: string | null;
}
export interface SummaryPanelResponse {
  maintenance: SummaryMaintenance;
}
export interface SummaryRealtimeSnapshot {
  projectId: string;
  projectRevision: number | null;
  summary: { statuses: SummaryStatusItem[]; maintenance: SummaryMaintenance };
}
export interface ChapterSummaryListItem {
  chapterId: string;
  chapterOrder: number;
  volumeId: string | null;
  volumeTitle: string | null;
  volumeOrder: number | null;
  chapterTitle: string;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  startTime: string;
  endTime: string;
  characters: string[];
  locations: string[];
  summary: string;
  errorMessage: string | null;
  updatedAt: string | null;
}
export interface ChapterSummaryListResponse {
  items: ChapterSummaryListItem[];
  total: number;
  page: number;
  pageSize: number;
}
export interface LongTermSummaryListResponse {
  items: LongTermSummaryListItem[];
  total: number;
  page: number;
  pageSize: number;
}
export interface MissingChapterSummaryItem {
  chapterId: string;
  chapterOrder: number;
  volumeId: string | null;
  volumeTitle: string | null;
  volumeOrder: number | null;
  chapterTitle: string;
  wordCount: number;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  progressMessage: string | null;
}
export interface MissingLongTermSummaryItem {
  startOrder: number;
  endOrder: number;
  startVolumeTitle: string | null;
  startChapterTitle: string;
  endVolumeTitle: string | null;
  endChapterTitle: string;
  status: SummaryStatus;
  isStale: boolean;
  summaryId: string | null;
  progressMessage: string | null;
}
export interface SkippedChapterSummaryItem {
  chapterId: string;
  chapterOrder: number;
  volumeId: string | null;
  volumeTitle: string | null;
  volumeOrder: number | null;
  chapterTitle: string;
  wordCount: number;
}
export interface SummaryBackgroundJobItem {
  jobId: string;
  jobType: "chapter_summary" | "long_term_summary" | "summary_batch";
  status: string;
  chapterId: string | null;
  summaryId: string | null;
  startOrder: number | null;
  endOrder: number | null;
  progressCurrent: number;
  progressTotal: number | null;
  progressMessage: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}
export interface SummaryBatchProgressItem {
  jobId: string;
  status: string;
  progressCurrent: number;
  progressTotal: number | null;
  progressPercent: number | null;
  progressMessage: string | null;
  totalItemCount: number;
  completedItemCount: number;
  runningItemCount: number;
  queuedItemCount: number;
  createdAt: string;
  updatedAt: string;
}
export interface SummaryMaintenance {
  autoGenerationBlocked: boolean;
  blockReasonCode: string | null;
  blockReasonParams: Record<string, number | string> | null;
  missingOrFailedChapterSummaries: MissingChapterSummaryItem[];
  missingOrFailedLongTermSummaries: MissingLongTermSummaryItem[];
  skippedChapterSummaries: SkippedChapterSummaryItem[];
  batchProgress: SummaryBatchProgressItem | null;
  activeJobs: SummaryBackgroundJobItem[];
}
export interface EnqueueSummaryRequest {
  summaryType: "chapter" | "long_term" | "all";
  chapterId?: string;
  startOrder?: number;
  endOrder?: number;
}
export interface EnqueueSummaryResponse {
  summaryId: string | null;
  status: string;
  jobId: string | null;
  itemCount: number;
}

function transformSummaryStatusItem(raw: Record<string, unknown>): SummaryStatusItem {
  return {
    chapterId: raw.chapter_id as string,
    volumeId: (raw.volume_id as string | null) ?? null,
    status: raw.status as SummaryStatus,
    isStale: Boolean(raw.is_stale),
    summaryId: raw.summary_id as string | null,
    updatedAt: raw.updated_at as string | null,
  };
}
function transformLongTermSummaryListItem(raw: Record<string, unknown>): LongTermSummaryListItem {
  return {
    startOrder: Number(raw.start_order ?? 0),
    endOrder: Number(raw.end_order ?? 0),
    startVolumeTitle: (raw.start_volume_title as string | null) ?? null,
    startChapterTitle: (raw.start_chapter_title as string) || "",
    endVolumeTitle: (raw.end_volume_title as string | null) ?? null,
    endChapterTitle: (raw.end_chapter_title as string) || "",
    status: raw.status as SummaryStatus,
    isStale: Boolean(raw.is_stale),
    summaryId: raw.summary_id as string | null,
    startTime: (raw.start_time as string) || "",
    endTime: (raw.end_time as string) || "",
    summary: (raw.summary as string) || "",
    errorMessage: raw.error_message as string | null,
    updatedAt: raw.updated_at as string | null,
  };
}
function transformChapterSummaryListItem(raw: Record<string, unknown>): ChapterSummaryListItem {
  return {
    chapterId: raw.chapter_id as string,
    chapterOrder: Number(raw.chapter_order ?? 0),
    volumeId: (raw.volume_id as string | null) ?? null,
    volumeTitle: (raw.volume_title as string | null) ?? null,
    volumeOrder: raw.volume_order == null ? null : Number(raw.volume_order),
    chapterTitle: (raw.chapter_title as string) || "未命名章节",
    status: raw.status as SummaryStatus,
    isStale: Boolean(raw.is_stale),
    summaryId: raw.summary_id as string | null,
    startTime: (raw.start_time as string) || "",
    endTime: (raw.end_time as string) || "",
    characters: (raw.characters as string[]) || [],
    locations: (raw.locations as string[]) || [],
    summary: (raw.summary as string) || "",
    errorMessage: raw.error_message as string | null,
    updatedAt: raw.updated_at as string | null,
  };
}
function transformSummaryMaintenance(raw: Record<string, unknown>): SummaryMaintenance {
  const batch = raw.batch_progress as Record<string, unknown> | undefined;
  return {
    autoGenerationBlocked: Boolean(raw.auto_generation_blocked),
    blockReasonCode: (raw.block_reason_code as string | null) ?? null,
    blockReasonParams: (raw.block_reason_params as Record<string, number | string> | null) ?? null,
    missingOrFailedChapterSummaries: (
      (raw.missing_or_failed_chapter_summaries as Record<string, unknown>[]) || []
    ).map((item) => ({
      chapterId: item.chapter_id as string,
      chapterOrder: item.chapter_order as number,
      volumeId: (item.volume_id as string | null) ?? null,
      volumeTitle: (item.volume_title as string | null) ?? null,
      volumeOrder: item.volume_order == null ? null : Number(item.volume_order),
      chapterTitle: item.chapter_title as string,
      wordCount: Number(item.word_count ?? 0),
      status: item.status as SummaryStatus,
      isStale: Boolean(item.is_stale),
      summaryId: item.summary_id as string | null,
      progressMessage: (item.progress_message as string | null) ?? null,
    })),
    missingOrFailedLongTermSummaries: (
      (raw.missing_or_failed_long_term_summaries as Record<string, unknown>[]) || []
    ).map((item) => ({
      startOrder: item.start_order as number,
      endOrder: item.end_order as number,
      startVolumeTitle: (item.start_volume_title as string | null) ?? null,
      startChapterTitle: (item.start_chapter_title as string) || "",
      endVolumeTitle: (item.end_volume_title as string | null) ?? null,
      endChapterTitle: (item.end_chapter_title as string) || "",
      status: item.status as SummaryStatus,
      isStale: Boolean(item.is_stale),
      summaryId: item.summary_id as string | null,
      progressMessage: (item.progress_message as string | null) ?? null,
    })),
    skippedChapterSummaries: (
      (raw.skipped_chapter_summaries as Record<string, unknown>[]) || []
    ).map((item) => ({
      chapterId: item.chapter_id as string,
      chapterOrder: Number(item.chapter_order ?? 0),
      volumeId: (item.volume_id as string | null) ?? null,
      volumeTitle: (item.volume_title as string | null) ?? null,
      volumeOrder: item.volume_order == null ? null : Number(item.volume_order),
      chapterTitle: (item.chapter_title as string) || "未命名章节",
      wordCount: Number(item.word_count ?? 0),
    })),
    batchProgress: batch
      ? {
          jobId: batch.job_id as string,
          status: batch.status as string,
          progressCurrent: Number(batch.progress_current ?? 0),
          progressTotal: batch.progress_total == null ? null : Number(batch.progress_total),
          progressPercent: batch.progress_percent == null ? null : Number(batch.progress_percent),
          progressMessage: (batch.progress_message as string | null) ?? null,
          totalItemCount: Number(batch.total_item_count ?? 0),
          completedItemCount: Number(batch.completed_item_count ?? 0),
          runningItemCount: Number(batch.running_item_count ?? 0),
          queuedItemCount: Number(batch.queued_item_count ?? 0),
          createdAt: batch.created_at as string,
          updatedAt: batch.updated_at as string,
        }
      : null,
    activeJobs: ((raw.active_jobs as Record<string, unknown>[]) || []).map((item) => ({
      jobId: item.job_id as string,
      jobType: item.job_type as "chapter_summary" | "long_term_summary" | "summary_batch",
      status: item.status as string,
      chapterId: (item.chapter_id as string | null) ?? null,
      summaryId: (item.summary_id as string | null) ?? null,
      startOrder: (item.start_order as number | null) ?? null,
      endOrder: (item.end_order as number | null) ?? null,
      progressCurrent: Number(item.progress_current ?? 0),
      progressTotal: item.progress_total == null ? null : Number(item.progress_total),
      progressMessage: (item.progress_message as string | null) ?? null,
      errorMessage: (item.error_message as string | null) ?? null,
      createdAt: item.created_at as string,
      updatedAt: item.updated_at as string,
    })),
  };
}
export function transformSummaryRealtimeSnapshot(
  raw: Record<string, unknown>,
): SummaryRealtimeSnapshot {
  const summary = (raw.summary as Record<string, unknown>) || {};
  return {
    projectId: raw.project_id as string,
    projectRevision: raw.project_revision == null ? null : Number(raw.project_revision),
    summary: {
      statuses: ((summary.statuses as Record<string, unknown>[]) || []).map(
        transformSummaryStatusItem,
      ),
      maintenance: transformSummaryMaintenance(
        (summary.maintenance as Record<string, unknown>) || {},
      ),
    },
  };
}
export async function fetchChapterSummaryList(
  projectId: string,
  page: number,
  pageSize = 20,
  signal?: AbortSignal,
  volumeId?: string | null,
  query?: string,
): Promise<ChapterSummaryListResponse> {
  const response = await apiClient.get<Record<string, unknown>>(
    `/projects/${projectId}/chapter-context/summaries/chapters`,
    {
      params: {
        page,
        page_size: pageSize,
        ...(volumeId ? { volume_id: volumeId } : {}),
        ...(query ? { q: query } : {}),
      },
      signal,
    },
  );
  return {
    items: ((response.data.items as Record<string, unknown>[]) || []).map(
      transformChapterSummaryListItem,
    ),
    total: Number(response.data.total ?? 0),
    page: Number(response.data.page ?? page),
    pageSize: Number(response.data.page_size ?? pageSize),
  };
}
export async function deleteChapterSummaries(
  projectId: string,
  chapterIds: string[],
): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/chapter-context/summaries/chapters`, {
    data: { chapter_ids: chapterIds },
  });
}
export async function deleteLongTermSummaries(
  projectId: string,
  ranges: Array<[number, number]>,
): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/chapter-context/summaries/long-term`, {
    data: { ranges },
  });
}
export async function fetchLongTermSummariesPage(
  projectId: string,
  page: number,
  pageSize = 20,
  signal?: AbortSignal,
  query?: string,
): Promise<LongTermSummaryListResponse> {
  const response = await apiClient.get<Record<string, unknown>>(
    `/projects/${projectId}/chapter-context/summaries/long-term`,
    { params: { page, page_size: pageSize, ...(query ? { q: query } : {}) }, signal },
  );
  return {
    items: ((response.data.items as Record<string, unknown>[]) || []).map(
      transformLongTermSummaryListItem,
    ),
    total: Number(response.data.total ?? 0),
    page: Number(response.data.page ?? page),
    pageSize: Number(response.data.page_size ?? pageSize),
  };
}
export async function enqueueSummary(
  projectId: string,
  data: EnqueueSummaryRequest,
): Promise<EnqueueSummaryResponse> {
  const response = await apiClient.post<Record<string, unknown>>(
    `/projects/${projectId}/chapter-context/summaries/enqueue`,
    {
      summary_type: data.summaryType,
      chapter_id: data.chapterId,
      start_order: data.startOrder,
      end_order: data.endOrder,
    },
  );
  return {
    summaryId: (response.data.summary_id as string | null) ?? null,
    status: (response.data.status as string) || "queued",
    jobId: (response.data.job_id as string | null) ?? null,
    itemCount: Number(response.data.item_count ?? 0),
  };
}
export async function cancelBackgroundJob(jobId: string, reason: string): Promise<void> {
  await apiClient.post(`/background/jobs/${jobId}/cancel`, { reason });
}
