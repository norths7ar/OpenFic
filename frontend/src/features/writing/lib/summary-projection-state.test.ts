import { describe, expect, test } from "vite-plus/test";

import type { SummaryBackgroundJobItem, SummaryBatchProgressItem } from "./summary-api";
import {
  applyChapterStatusToProjection,
  applyItemEventToProjection,
  applyJobEventToProjection,
  applyLongTermStatusToProjection,
  createEmptySummaryProjection,
  isSummaryBackgroundEvent,
  isSummaryEventForProject,
  normalizeRevision,
  reduceSummaryProjectionEvent,
  shouldApplyEventRevision,
  shouldApplySnapshotRevision,
  type SummaryBackgroundEvent,
  type SummaryProjection,
} from "./summary-projection-state";

function event(overrides: Partial<SummaryBackgroundEvent> = {}): SummaryBackgroundEvent {
  return {
    type: "background_item_progress",
    job_type: "chapter_summary",
    project_id: "project-a",
    job_id: "job-a",
    item_id: "job-a",
    item_type: "chapter_summary",
    created_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function projection(overrides: Partial<SummaryProjection> = {}): SummaryProjection {
  return {
    ...createEmptySummaryProjection("project-a"),
    ...overrides,
  };
}

function activeJob(overrides: Partial<SummaryBackgroundJobItem> = {}): SummaryBackgroundJobItem {
  return {
    jobId: "job-a",
    jobType: "chapter_summary",
    status: "running",
    chapterId: "chapter-a",
    summaryId: null,
    startOrder: null,
    endOrder: null,
    progressCurrent: 1,
    progressTotal: 3,
    progressMessage: null,
    errorMessage: null,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function batchProgress(
  overrides: Partial<SummaryBatchProgressItem> = {},
): SummaryBatchProgressItem {
  return {
    jobId: "job-a",
    status: "running",
    progressCurrent: 1,
    progressTotal: 3,
    progressPercent: 33,
    progressMessage: null,
    totalItemCount: 1,
    completedItemCount: 0,
    runningItemCount: 1,
    queuedItemCount: 0,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("summary projection state", () => {
  test("filters summary events by project and event family", () => {
    expect(isSummaryEventForProject("project-a", event())).toBe(true);
    expect(isSummaryEventForProject("project-b", event())).toBe(false);
    expect(
      isSummaryBackgroundEvent(
        event({ type: "background_job_started", job_type: "index", item_type: null }),
      ),
    ).toBe(false);
  });

  test("rejects old event revisions but accepts equal snapshot revisions", () => {
    expect(normalizeRevision("12")).toBe(12);
    expect(shouldApplyEventRevision(12, 12)).toBe(false);
    expect(shouldApplyEventRevision(12, 13)).toBe(true);
    expect(shouldApplySnapshotRevision(12, 11)).toBe(false);
    expect(shouldApplySnapshotRevision(12, 12)).toBe(true);
  });

  test("updates chapter status and removes a completed chapter from maintenance", () => {
    const initial = projection({
      statuses: [
        {
          chapterId: "chapter-a",
          volumeId: "volume-a",
          status: "running",
          isStale: false,
          summaryId: null,
          updatedAt: null,
        },
      ],
      maintenance: {
        ...createEmptySummaryProjection("project-a").maintenance,
        missingOrFailedChapterSummaries: [
          {
            chapterId: "chapter-a",
            chapterOrder: 1,
            volumeId: "volume-a",
            volumeTitle: "Volume",
            volumeOrder: 1,
            chapterTitle: "Chapter",
            wordCount: 20,
            status: "running",
            isStale: false,
            summaryId: null,
            progressMessage: "working",
          },
        ],
      },
    });

    const next = applyChapterStatusToProjection(initial, {
      chapter_id: "chapter-a",
      status: "ready",
      is_stale: false,
      summary_id: "summary-a",
    });

    expect(next.statuses[0]).toMatchObject({ status: "ready", summaryId: "summary-a" });
    expect(next.maintenance.missingOrFailedChapterSummaries).toEqual([]);
  });

  test("adds a long-term failure to maintenance and clears it when ready", () => {
    const failed = applyLongTermStatusToProjection(projection(), {
      start_order: 1,
      end_order: 3,
      status: "failed",
      progress_message: "failed",
    });
    expect(failed.maintenance.missingOrFailedLongTermSummaries).toHaveLength(1);

    const ready = applyLongTermStatusToProjection(failed, {
      start_order: 1,
      end_order: 3,
      status: "ready",
      is_stale: false,
    });
    expect(ready.maintenance.missingOrFailedLongTermSummaries).toEqual([]);
  });

  test("tracks item queue, progress, and terminal removal", () => {
    const queued = applyItemEventToProjection(
      projection(),
      event({ type: "background_item_queued", payload: { chapter_id: "chapter-a" } }),
    );
    expect(queued.maintenance.activeJobs[0]).toMatchObject({ status: "pending" });
    expect(queued.maintenance.batchProgress).toMatchObject({ queuedItemCount: 1 });

    const running = applyItemEventToProjection(
      queued,
      event({ type: "background_item_progress", payload: { current: 2, total: 3 } }),
    );
    expect(running.maintenance.activeJobs[0]).toMatchObject({
      status: "running",
      progressCurrent: 2,
      progressTotal: 3,
    });

    const completed = applyItemEventToProjection(
      running,
      event({ type: "background_item_succeeded", payload: { status: "ready" } }),
    );
    expect(completed.maintenance.activeJobs).toEqual([]);
    expect(completed.maintenance.batchProgress).toMatchObject({ completedItemCount: 1 });
  });

  test("updates and terminates a batch job progress record", () => {
    const initial = projection({
      maintenance: {
        ...createEmptySummaryProjection("project-a").maintenance,
        activeJobs: [activeJob()],
        batchProgress: batchProgress(),
      },
    });
    const progressed = applyJobEventToProjection(
      initial,
      event({
        type: "background_job_progress",
        job_type: "summary_batch",
        item_id: null,
        payload: { current: 2, total: 3, progress_percent: 66 },
      }),
    );
    expect(progressed.maintenance.activeJobs[0]).toMatchObject({ progressCurrent: 2 });

    const completed = applyJobEventToProjection(
      progressed,
      event({
        type: "background_job_succeeded",
        job_type: "summary_batch",
        item_id: null,
        payload: {},
      }),
    );
    expect(completed.maintenance.activeJobs).toEqual([]);
    expect(completed.maintenance.batchProgress).toMatchObject({
      status: "succeeded",
      progressPercent: 100,
    });
  });

  test("reduces a current event and advances its revision", () => {
    const next = reduceSummaryProjectionEvent(
      projection({ projectRevision: 4 }),
      event({
        type: "chapter_summary_updated",
        item_type: null,
        payload: { chapter_id: "chapter-a", status: "queued" },
        project_revision: 5,
      }),
    );
    expect(next.projectRevision).toBe(5);
    expect(next.statuses[0]).toMatchObject({ chapterId: "chapter-a", status: "queued" });
  });
});
