import type {
  SummaryBackgroundJobItem,
  SummaryMaintenance,
  SummaryStatus,
  SummaryStatusItem,
} from "./summary-api";
import {
  extractBatchProgressFromEvent,
  ITEM_TERMINAL_EVENT_TYPES,
  updateBatchProgressForItemEvent,
} from "./summary-batch-progress";

export interface SummaryBackgroundEvent {
  type: string;
  job_type: string;
  job_id?: string;
  item_id?: string | null;
  item_type?: string | null;
  project_id?: string | null;
  payload?: Record<string, unknown>;
  created_at?: string;
  project_revision?: number | null;
}

export const SUMMARY_JOB_TYPES = new Set(["chapter_summary", "long_term_summary", "summary_batch"]);
export const SUMMARY_ITEM_TYPES = new Set(["chapter_summary", "long_term_summary"]);
export const SUMMARY_EVENT_TYPES = new Set([
  "background_job_started",
  "background_job_progress",
  "background_job_succeeded",
  "background_job_failed",
  "background_job_skipped",
  "background_job_cancel_requested",
  "background_job_cancelled",
  "background_item_queued",
  "background_item_progress",
  "background_item_succeeded",
  "background_item_failed",
  "background_item_skipped",
  "chapter_summary_updated",
  "long_term_summary_updated",
]);

export interface SummaryProjection {
  projectId: string;
  projectRevision: number | null;
  statuses: SummaryStatusItem[];
  maintenance: SummaryMaintenance;
}

export function isSummaryBackgroundEvent(event: SummaryBackgroundEvent): boolean {
  if (!SUMMARY_EVENT_TYPES.has(event.type)) return false;
  if (event.type === "chapter_summary_updated" || event.type === "long_term_summary_updated") {
    return true;
  }
  if (typeof event.job_type === "string" && SUMMARY_JOB_TYPES.has(event.job_type)) {
    return true;
  }
  if (typeof event.item_type === "string" && SUMMARY_ITEM_TYPES.has(event.item_type)) {
    return true;
  }
  return false;
}

export function isSummaryEventForProject(
  projectId: string,
  event: SummaryBackgroundEvent,
): boolean {
  return event.project_id === projectId && isSummaryBackgroundEvent(event);
}

export function createEmptySummaryMaintenance(): SummaryMaintenance {
  return {
    autoGenerationBlocked: false,
    blockReasonCode: null,
    blockReasonParams: null,
    missingOrFailedChapterSummaries: [],
    missingOrFailedLongTermSummaries: [],
    skippedChapterSummaries: [],
    batchProgress: null,
    activeJobs: [],
  };
}

export function createEmptySummaryProjection(projectId: string): SummaryProjection {
  return {
    projectId,
    projectRevision: null,
    statuses: [],
    maintenance: createEmptySummaryMaintenance(),
  };
}

export function normalizeRevision(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function shouldApplyEventRevision(
  currentRevision: number | null,
  eventRevision: number | null,
): boolean {
  if (eventRevision == null) return true;
  if (currentRevision == null) return true;
  return eventRevision > currentRevision;
}

export function shouldApplySnapshotRevision(
  currentRevision: number | null,
  snapshotRevision: number | null,
): boolean {
  if (snapshotRevision == null) return true;
  if (currentRevision == null) return true;
  return snapshotRevision >= currentRevision;
}

export function getString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function getNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function getBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function normalizeSummaryStatus(value: unknown): SummaryStatus | null {
  if (
    value === "not_generated" ||
    value === "queued" ||
    value === "running" ||
    value === "ready" ||
    value === "failed"
  ) {
    return value;
  }
  if (value === "succeeded") return "ready";
  if (value === "failed") return "failed";
  return null;
}

export function resolveSummaryId(
  payload: Record<string, unknown>,
  current: string | null,
): string | null {
  if (!("summary_id" in payload)) return current;
  return getString(payload.summary_id);
}

export function resolveUpdatedAt(
  payload: Record<string, unknown>,
  current: string | null,
): string | null {
  if (!("updated_at" in payload)) return current;
  return getString(payload.updated_at);
}

export function resolveProgressMessage(
  payload: Record<string, unknown>,
  current: string | null,
): string | null {
  if ("progress_message" in payload) return getString(payload.progress_message);
  if ("message" in payload) return getString(payload.message);
  return current;
}

export function applyChapterStatusToProjection(
  projection: SummaryProjection,
  payload: Record<string, unknown>,
): SummaryProjection {
  const chapterId = getString(payload.chapter_id);
  const status = normalizeSummaryStatus(payload.status);
  if (!chapterId || !status) return projection;

  const isStale = getBoolean(payload.is_stale);
  const progressMessage = status === "ready" ? null : resolveProgressMessage(payload, null);
  let statusFound = false;
  const statuses = projection.statuses.map((item) => {
    if (item.chapterId !== chapterId) return item;
    statusFound = true;
    return {
      ...item,
      status,
      isStale,
      summaryId: resolveSummaryId(payload, item.summaryId),
      updatedAt: resolveUpdatedAt(payload, item.updatedAt),
    };
  });
  if (!statusFound) {
    statuses.push({
      chapterId,
      volumeId: null,
      status,
      isStale,
      summaryId: resolveSummaryId(payload, null),
      updatedAt: resolveUpdatedAt(payload, null),
    });
  }

  let missingFound = false;
  const missingOrFailedChapterSummaries = projection.maintenance.missingOrFailedChapterSummaries
    .map((item) => {
      if (item.chapterId !== chapterId) return item;
      missingFound = true;
      return {
        ...item,
        status,
        isStale,
        summaryId: resolveSummaryId(payload, item.summaryId),
        progressMessage:
          status === "ready" ? null : resolveProgressMessage(payload, item.progressMessage),
      };
    })
    .filter((item) => !(item.chapterId === chapterId && item.status === "ready" && !item.isStale));

  const chapterOrder = getNumber(payload.chapter_order);
  if (!missingFound && !(status === "ready" && !isStale) && chapterOrder != null) {
    missingOrFailedChapterSummaries.push({
      chapterId,
      chapterOrder,
      volumeId: null,
      volumeTitle: null,
      volumeOrder: null,
      chapterTitle: getString(payload.chapter_title) ?? chapterId,
      wordCount: getNumber(payload.word_count) ?? 0,
      status,
      isStale,
      summaryId: resolveSummaryId(payload, null),
      progressMessage,
    });
  }

  return {
    ...projection,
    statuses,
    maintenance: {
      ...projection.maintenance,
      missingOrFailedChapterSummaries,
    },
  };
}

export function applyLongTermStatusToProjection(
  projection: SummaryProjection,
  payload: Record<string, unknown>,
): SummaryProjection {
  const startOrder = getNumber(payload.start_order);
  const endOrder = getNumber(payload.end_order);
  const status = normalizeSummaryStatus(payload.status);
  if (startOrder == null || endOrder == null || !status) return projection;

  const isStale = getBoolean(payload.is_stale);
  let found = false;
  const missingOrFailedLongTermSummaries = projection.maintenance.missingOrFailedLongTermSummaries
    .map((item) => {
      if (item.startOrder !== startOrder || item.endOrder !== endOrder) return item;
      found = true;
      return {
        ...item,
        status,
        isStale,
        summaryId: resolveSummaryId(payload, item.summaryId),
        progressMessage:
          status === "ready" ? null : resolveProgressMessage(payload, item.progressMessage),
      };
    })
    .filter(
      (item) =>
        !(
          item.startOrder === startOrder &&
          item.endOrder === endOrder &&
          item.status === "ready" &&
          !item.isStale
        ),
    );

  if (!found && !(status === "ready" && !isStale)) {
    missingOrFailedLongTermSummaries.push({
      startOrder,
      endOrder,
      startVolumeTitle: null,
      startChapterTitle: "",
      endVolumeTitle: null,
      endChapterTitle: "",
      status,
      isStale,
      summaryId: resolveSummaryId(payload, null),
      progressMessage: status === "ready" ? null : resolveProgressMessage(payload, null),
    });
  }

  return {
    ...projection,
    maintenance: {
      ...projection.maintenance,
      missingOrFailedLongTermSummaries,
    },
  };
}

export function buildActiveJobFromEvent(
  event: SummaryBackgroundEvent,
  existing: SummaryBackgroundJobItem | undefined,
): SummaryBackgroundJobItem | null {
  const jobId = getString(event.item_id) ?? getString(event.job_id);
  const payload = event.payload ?? {};
  const jobType =
    event.item_type === "chapter_summary" || event.item_type === "long_term_summary"
      ? event.item_type
      : event.job_type === "chapter_summary" ||
          event.job_type === "long_term_summary" ||
          event.job_type === "summary_batch"
        ? event.job_type
        : null;
  if (!jobId || !jobType) return null;

  const now = event.created_at ?? new Date().toISOString();
  return {
    jobId,
    jobType,
    status: event.type === "background_item_queued" ? "pending" : "running",
    chapterId: getString(payload.chapter_id) ?? existing?.chapterId ?? null,
    summaryId: resolveSummaryId(payload, existing?.summaryId ?? null),
    startOrder: getNumber(payload.start_order) ?? existing?.startOrder ?? null,
    endOrder: getNumber(payload.end_order) ?? existing?.endOrder ?? null,
    progressCurrent:
      getNumber(payload.progress_current) ??
      getNumber(payload.current) ??
      existing?.progressCurrent ??
      0,
    progressTotal:
      "progress_total" in payload
        ? getNumber(payload.progress_total)
        : (getNumber(payload.total) ?? existing?.progressTotal ?? null),
    progressMessage: resolveProgressMessage(payload, existing?.progressMessage ?? null),
    errorMessage:
      "error_message" in payload
        ? getString(payload.error_message)
        : (existing?.errorMessage ?? null),
    createdAt: existing?.createdAt ?? now,
    updatedAt: now,
  };
}

export function applyItemEventToProjection(
  projection: SummaryProjection,
  event: SummaryBackgroundEvent,
): SummaryProjection {
  const jobId = getString(event.item_id) ?? getString(event.job_id);
  const payload = event.payload ?? {};
  let next = projection;

  if (event.item_type === "chapter_summary") {
    next = applyChapterStatusToProjection(next, payload);
  } else if (event.item_type === "long_term_summary") {
    next = applyLongTermStatusToProjection(next, payload);
  }

  const previousJob = jobId
    ? next.maintenance.activeJobs.find((job) => job.jobId === jobId)
    : undefined;
  const activeJobs = ITEM_TERMINAL_EVENT_TYPES.has(event.type)
    ? next.maintenance.activeJobs.filter((job) => job.jobId !== jobId)
    : (() => {
        const nextJob = buildActiveJobFromEvent(event, previousJob);
        if (!nextJob) return next.maintenance.activeJobs;
        return [
          ...next.maintenance.activeJobs.filter((job) => job.jobId !== nextJob.jobId),
          nextJob,
        ];
      })();

  return {
    ...next,
    maintenance: {
      ...next.maintenance,
      activeJobs,
      batchProgress: updateBatchProgressForItemEvent(
        next.maintenance.batchProgress,
        event,
        previousJob,
      ),
    },
  };
}

export function applyJobEventToProjection(
  projection: SummaryProjection,
  event: SummaryBackgroundEvent,
): SummaryProjection {
  const jobId = getString(event.job_id);
  const itemId = getString(event.item_id);
  if (!jobId && !itemId) return projection;

  if (event.type === "background_job_started" || event.type === "background_job_progress") {
    const batchProgress =
      event.type === "background_job_progress"
        ? extractBatchProgressFromEvent(event, projection.maintenance.batchProgress)
        : projection.maintenance.batchProgress?.jobId === jobId
          ? {
              ...projection.maintenance.batchProgress,
              status: "running",
              updatedAt: event.created_at ?? projection.maintenance.batchProgress.updatedAt,
            }
          : projection.maintenance.batchProgress;

    return {
      ...projection,
      maintenance: {
        ...projection.maintenance,
        batchProgress,
        activeJobs: projection.maintenance.activeJobs.map((job) =>
          (itemId != null ? job.jobId === itemId : job.jobId === jobId)
            ? {
                ...job,
                status: event.type === "background_job_started" ? "running" : job.status,
                progressCurrent:
                  getNumber(event.payload?.current) ??
                  getNumber(event.payload?.progress_current) ??
                  job.progressCurrent,
                progressTotal:
                  getNumber(event.payload?.total) ??
                  getNumber(event.payload?.progress_total) ??
                  job.progressTotal,
                progressMessage:
                  getString(event.payload?.message) ??
                  getString(event.payload?.progress_message) ??
                  job.progressMessage,
                updatedAt: event.created_at ?? job.updatedAt,
              }
            : job,
        ),
      },
    };
  }

  if (event.type === "background_job_cancel_requested") {
    return {
      ...projection,
      maintenance: {
        ...projection.maintenance,
        batchProgress:
          jobId && projection.maintenance.batchProgress?.jobId === jobId
            ? {
                ...projection.maintenance.batchProgress,
                status: "cancel_requested",
                progressMessage: "batch_cancelling",
                updatedAt: event.created_at ?? projection.maintenance.batchProgress.updatedAt,
              }
            : projection.maintenance.batchProgress,
        activeJobs: projection.maintenance.activeJobs.map((job) =>
          job.jobId === jobId ? { ...job, status: "cancel_requested" } : job,
        ),
      },
    };
  }

  if (
    event.type === "background_job_succeeded" ||
    event.type === "background_job_failed" ||
    event.type === "background_job_skipped" ||
    event.type === "background_job_cancelled"
  ) {
    const currentBatchProgress =
      jobId && projection.maintenance.batchProgress?.jobId === jobId
        ? projection.maintenance.batchProgress
        : null;
    const terminalStatus =
      event.type === "background_job_succeeded"
        ? "succeeded"
        : event.type === "background_job_failed"
          ? "failed"
          : event.type === "background_job_skipped"
            ? "skipped"
            : "cancelled";
    const batchProgress = currentBatchProgress
      ? {
          ...currentBatchProgress,
          status: terminalStatus,
          completedItemCount:
            event.type === "background_job_succeeded"
              ? Math.max(
                  currentBatchProgress.completedItemCount,
                  currentBatchProgress.totalItemCount,
                )
              : currentBatchProgress.completedItemCount,
          progressCurrent:
            event.type === "background_job_succeeded"
              ? (currentBatchProgress.progressTotal ?? currentBatchProgress.progressCurrent)
              : currentBatchProgress.progressCurrent,
          progressPercent:
            event.type === "background_job_succeeded" ? 100 : currentBatchProgress.progressPercent,
          progressMessage:
            getString(event.payload?.message) ??
            getString(event.payload?.progress_message) ??
            currentBatchProgress.progressMessage,
          queuedItemCount: 0,
          runningItemCount: 0,
          updatedAt: event.created_at ?? currentBatchProgress.updatedAt,
        }
      : projection.maintenance.batchProgress;

    return {
      ...projection,
      maintenance: {
        ...projection.maintenance,
        batchProgress,
        activeJobs: projection.maintenance.activeJobs.filter((job) =>
          itemId != null ? job.jobId !== itemId : job.jobId !== jobId,
        ),
      },
    };
  }

  return projection;
}

export function reduceSummaryProjectionEvent(
  projection: SummaryProjection,
  event: SummaryBackgroundEvent,
): SummaryProjection {
  let next = projection;
  if (event.type === "chapter_summary_updated" && event.payload) {
    next = applyChapterStatusToProjection(next, event.payload);
  } else if (event.type === "long_term_summary_updated" && event.payload) {
    next = applyLongTermStatusToProjection(next, event.payload);
  } else if (event.type.startsWith("background_item_")) {
    next = applyItemEventToProjection(next, event);
  } else {
    next = applyJobEventToProjection(next, event);
  }

  const eventRevision = normalizeRevision(event.project_revision);
  return eventRevision == null ? next : { ...next, projectRevision: eventRevision };
}
