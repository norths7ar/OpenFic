import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useEffect } from "react";

import {
  subscribeBackgroundProjection,
  type BackgroundEvent,
  type BackgroundProjectionSubscription,
  type BackgroundSnapshot,
} from "@/features/assistant/lib/agent-runtime-api";
import { requestBackgroundSnapshot } from "@/lib/background-socket";

import {
  cancelBackgroundJob,
  deleteChapterSummaries,
  deleteLongTermSummaries,
  enqueueSummary,
  fetchChapterSummaryList,
  fetchLongTermSummariesPage,
  transformSummaryRealtimeSnapshot,
  type ChapterSummaryListResponse,
  type EnqueueSummaryRequest,
  type LongTermSummaryListResponse,
  type SummaryBackgroundJobItem,
  type SummaryPanelResponse,
  type SummaryStatusItem,
} from "../lib/summary-api";
import {
  applyChapterStatusToProjection,
  applyLongTermStatusToProjection,
  createEmptySummaryProjection,
  getBoolean,
  getNumber,
  getString,
  isSummaryEventForProject,
  normalizeRevision,
  normalizeSummaryStatus,
  reduceSummaryProjectionEvent,
  resolveSummaryId,
  resolveUpdatedAt,
  shouldApplyEventRevision,
  shouldApplySnapshotRevision,
  type SummaryProjection,
} from "../lib/summary-projection-state";

const SUMMARY_PAGE_SIZE = 20;
const SUMMARY_PROJECTION_QUERY_KEY = "summary-projection";

const summaryProjectionSubscriptions = new Map<
  string,
  { count: number; subscription: BackgroundProjectionSubscription }
>();

function getSummaryProjectionQueryKey(projectId: string) {
  return [SUMMARY_PROJECTION_QUERY_KEY, projectId] as const;
}

function getProjection(queryClient: QueryClient, projectId: string): SummaryProjection {
  return (
    queryClient.getQueryData<SummaryProjection>(getSummaryProjectionQueryKey(projectId)) ??
    createEmptySummaryProjection(projectId)
  );
}

function applyChapterStatusToListQueries(
  queryClient: QueryClient,
  projectId: string,
  payload: Record<string, unknown>,
) {
  const chapterId = getString(payload.chapter_id);
  const status = normalizeSummaryStatus(payload.status);
  if (!chapterId || !status) return;

  queryClient.setQueriesData(
    { queryKey: ["chapter-summary-list", projectId] },
    (current: ChapterSummaryListResponse | undefined) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item) =>
          item.chapterId === chapterId
            ? {
                ...item,
                status,
                isStale: getBoolean(payload.is_stale),
                summaryId: resolveSummaryId(payload, item.summaryId),
                updatedAt: resolveUpdatedAt(payload, item.updatedAt),
              }
            : item,
        ),
      };
    },
  );
}

function applyLongTermStatusToListQueries(
  queryClient: QueryClient,
  projectId: string,
  payload: Record<string, unknown>,
) {
  const startOrder = getNumber(payload.start_order);
  const endOrder = getNumber(payload.end_order);
  const status = normalizeSummaryStatus(payload.status);
  if (startOrder == null || endOrder == null || !status) return;

  queryClient.setQueriesData(
    { queryKey: ["long-term-summaries-page", projectId] },
    (current: LongTermSummaryListResponse | undefined) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item) =>
          item.startOrder === startOrder && item.endOrder === endOrder
            ? {
                ...item,
                status,
                isStale: getBoolean(payload.is_stale),
                summaryId: resolveSummaryId(payload, item.summaryId),
                updatedAt: resolveUpdatedAt(payload, item.updatedAt),
              }
            : item,
        ),
      };
    },
  );
}

function applySummaryEventToListQueries(
  queryClient: QueryClient,
  projectId: string,
  event: BackgroundEvent,
) {
  if (!event.payload) return;
  if (event.type === "chapter_summary_updated" || event.item_type === "chapter_summary") {
    applyChapterStatusToListQueries(queryClient, projectId, event.payload);
  }
  if (event.type === "long_term_summary_updated" || event.item_type === "long_term_summary") {
    applyLongTermStatusToListQueries(queryClient, projectId, event.payload);
  }
}

function applySummarySnapshot(
  queryClient: QueryClient,
  projectId: string,
  snapshot: BackgroundSnapshot,
) {
  const transformed = transformSummaryRealtimeSnapshot(
    snapshot as unknown as Record<string, unknown>,
  );
  if (transformed.projectId !== projectId) return;

  const current = getProjection(queryClient, projectId);
  if (!shouldApplySnapshotRevision(current.projectRevision, transformed.projectRevision)) return;

  queryClient.setQueryData<SummaryProjection>(getSummaryProjectionQueryKey(projectId), {
    projectId,
    projectRevision: transformed.projectRevision,
    statuses: transformed.summary.statuses,
    maintenance: transformed.summary.maintenance,
  });
}

function applySummaryEvent(queryClient: QueryClient, projectId: string, event: BackgroundEvent) {
  if (!isSummaryEventForProject(projectId, event)) return;

  const current = getProjection(queryClient, projectId);
  const eventRevision = normalizeRevision(event.project_revision);
  if (!shouldApplyEventRevision(current.projectRevision, eventRevision)) return;

  queryClient.setQueryData<SummaryProjection>(
    getSummaryProjectionQueryKey(projectId),
    reduceSummaryProjectionEvent(current, event),
  );
  applySummaryEventToListQueries(queryClient, projectId, event);
}

function useSummaryProjectionSync(projectId: string) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!projectId) return;

    const existing = summaryProjectionSubscriptions.get(projectId);
    if (existing) {
      summaryProjectionSubscriptions.set(projectId, {
        ...existing,
        count: existing.count + 1,
      });
    } else {
      const subscription = subscribeBackgroundProjection(
        projectId,
        (snapshot) => applySummarySnapshot(queryClient, projectId, snapshot),
        (event) => applySummaryEvent(queryClient, projectId, event),
      );
      summaryProjectionSubscriptions.set(projectId, { count: 1, subscription });
    }

    return () => {
      const current = summaryProjectionSubscriptions.get(projectId);
      if (!current) return;
      if (current.count <= 1) {
        current.subscription.close();
        summaryProjectionSubscriptions.delete(projectId);
        return;
      }
      summaryProjectionSubscriptions.set(projectId, {
        ...current,
        count: current.count - 1,
      });
    };
  }, [projectId, queryClient]);
}

export function useSummaryStatuses(projectId: string) {
  const queryClient = useQueryClient();
  useSummaryProjectionSync(projectId);

  return useQuery<SummaryProjection, Error, SummaryStatusItem[]>({
    queryKey: getSummaryProjectionQueryKey(projectId),
    queryFn: async () => createEmptySummaryProjection(projectId),
    enabled: false,
    initialData: () => getProjection(queryClient, projectId),
    select: (projection) => projection.statuses,
    staleTime: Infinity,
  });
}

export function useSummaryPanel(projectId: string) {
  const queryClient = useQueryClient();
  useSummaryProjectionSync(projectId);

  return useQuery<SummaryProjection, Error, SummaryPanelResponse>({
    queryKey: getSummaryProjectionQueryKey(projectId),
    queryFn: async () => createEmptySummaryProjection(projectId),
    enabled: false,
    initialData: () => getProjection(queryClient, projectId),
    select: (projection) => ({ maintenance: projection.maintenance }),
    staleTime: Infinity,
  });
}

export function useChapterSummaryListPage(
  projectId: string,
  page: number,
  volumeId?: string | null,
  query?: string,
) {
  return useQuery<ChapterSummaryListResponse>({
    queryKey: [
      "chapter-summary-list",
      projectId,
      volumeId ?? "all",
      query ?? "",
      page,
      SUMMARY_PAGE_SIZE,
    ],
    queryFn: ({ signal }) =>
      fetchChapterSummaryList(projectId, page, SUMMARY_PAGE_SIZE, signal, volumeId, query),
    enabled: !!projectId,
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
}

export function useLongTermSummariesPage(projectId: string, page: number, query?: string) {
  return useQuery<LongTermSummaryListResponse>({
    queryKey: ["long-term-summaries-page", projectId, query ?? "", page, SUMMARY_PAGE_SIZE],
    queryFn: ({ signal }) =>
      fetchLongTermSummariesPage(projectId, page, SUMMARY_PAGE_SIZE, signal, query),
    enabled: !!projectId,
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
}

export function useEnqueueSummary(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EnqueueSummaryRequest) => enqueueSummary(projectId, data),
    onSuccess: (result, variables) => {
      const now = new Date().toISOString();
      const optimisticStatus = result.status === "ready" ? "ready" : "queued";
      const optimisticProgressMessage = optimisticStatus === "queued" ? "已加入队列" : null;
      const optimisticJob: SummaryBackgroundJobItem | null =
        result.jobId && variables.summaryType !== "all"
          ? {
              jobId: result.jobId,
              jobType:
                variables.summaryType === "chapter"
                  ? "chapter_summary"
                  : variables.summaryType === "long_term"
                    ? "long_term_summary"
                    : "chapter_summary",
              status: optimisticStatus === "queued" ? "pending" : "running",
              chapterId: variables.chapterId ?? null,
              summaryId: result.summaryId,
              startOrder: variables.startOrder ?? null,
              endOrder: variables.endOrder ?? null,
              progressCurrent: 0,
              progressTotal: null,
              progressMessage: optimisticProgressMessage,
              errorMessage: null,
              createdAt: now,
              updatedAt: now,
            }
          : null;

      queryClient.setQueryData<SummaryProjection>(
        getSummaryProjectionQueryKey(projectId),
        (current) => {
          let next = current ?? createEmptySummaryProjection(projectId);
          if (variables.summaryType === "chapter" && variables.chapterId) {
            next = applyChapterStatusToProjection(next, {
              chapter_id: variables.chapterId,
              status: optimisticStatus,
              summary_id: result.summaryId,
              progress_message: optimisticProgressMessage,
            });
          }
          if (
            variables.summaryType === "long_term" &&
            variables.startOrder != null &&
            variables.endOrder != null
          ) {
            next = applyLongTermStatusToProjection(next, {
              start_order: variables.startOrder,
              end_order: variables.endOrder,
              status: optimisticStatus,
              summary_id: result.summaryId,
              progress_message: optimisticProgressMessage,
            });
          }
          if (!optimisticJob) return next;
          return {
            ...next,
            maintenance: {
              ...next.maintenance,
              activeJobs: [
                ...next.maintenance.activeJobs.filter((item) => item.jobId !== optimisticJob.jobId),
                optimisticJob,
              ],
            },
          };
        },
      );

      queryClient.setQueriesData(
        { queryKey: ["chapter-summary-list", projectId] },
        (current: ChapterSummaryListResponse | undefined) => {
          if (!current || variables.summaryType !== "chapter" || !variables.chapterId)
            return current;
          return {
            ...current,
            items: current.items.map((item) =>
              item.chapterId === variables.chapterId
                ? {
                    ...item,
                    status: optimisticStatus,
                    isStale: optimisticStatus === "ready" ? item.isStale : false,
                    summaryId: result.summaryId,
                  }
                : item,
            ),
          };
        },
      );

      queryClient.setQueriesData(
        { queryKey: ["long-term-summaries-page", projectId] },
        (current: LongTermSummaryListResponse | undefined) => {
          if (!current || variables.summaryType !== "long_term") return current;
          return {
            ...current,
            items: current.items.map((item) =>
              item.startOrder === variables.startOrder && item.endOrder === variables.endOrder
                ? {
                    ...item,
                    status: optimisticStatus,
                    isStale: optimisticStatus === "ready" ? item.isStale : false,
                    summaryId: result.summaryId,
                  }
                : item,
            ),
          };
        },
      );

      void queryClient.invalidateQueries({ queryKey: ["chapter-summary-list", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["long-term-summaries-page", projectId] });
    },
  });
}

export function useCancelSummaryBatch(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => cancelBackgroundJob(jobId, "用户停止摘要生成队列"),
    onSuccess: (_result, jobId) => {
      queryClient.setQueryData<SummaryProjection>(
        getSummaryProjectionQueryKey(projectId),
        (current) => {
          if (
            !current ||
            current.maintenance.batchProgress?.jobId !== jobId ||
            (current.maintenance.batchProgress.status !== "pending" &&
              current.maintenance.batchProgress.status !== "running")
          ) {
            return current;
          }
          return {
            ...current,
            maintenance: {
              ...current.maintenance,
              batchProgress: {
                ...current.maintenance.batchProgress,
                status: "cancel_requested",
                progressMessage: "batch_cancelling",
                updatedAt: new Date().toISOString(),
              },
            },
          };
        },
      );
      void requestBackgroundSnapshot(projectId).catch(() => undefined);
    },
  });
}

export function useDeleteChapterSummaries(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (chapterIds: string[]) => deleteChapterSummaries(projectId, chapterIds),
    onMutate: async (chapterIds) => {
      await queryClient.cancelQueries({ queryKey: ["chapter-summary-list", projectId] });

      const previousChapterSummaryLists = queryClient.getQueriesData<ChapterSummaryListResponse>({
        queryKey: ["chapter-summary-list", projectId],
      });
      const previousSummaryProjection = queryClient.getQueryData<SummaryProjection>(
        getSummaryProjectionQueryKey(projectId),
      );
      const shouldClearAll = chapterIds.length === 0;
      const targetIdSet = new Set(chapterIds);

      queryClient.setQueriesData<ChapterSummaryListResponse>(
        { queryKey: ["chapter-summary-list", projectId] },
        (current) => {
          if (!current) return current;
          const nextItems = shouldClearAll
            ? []
            : current.items.filter((item) => !targetIdSet.has(item.chapterId));
          return {
            ...current,
            items: nextItems,
            total: shouldClearAll ? 0 : Math.max(0, current.total - targetIdSet.size),
          };
        },
      );

      queryClient.setQueryData<SummaryProjection>(
        getSummaryProjectionQueryKey(projectId),
        (current) => {
          if (!current) return current;
          return {
            ...current,
            statuses: current.statuses.map((item) =>
              shouldClearAll || targetIdSet.has(item.chapterId)
                ? {
                    ...item,
                    status: "not_generated",
                    isStale: false,
                    summaryId: null,
                    updatedAt: null,
                  }
                : item,
            ),
            maintenance: {
              ...current.maintenance,
              missingOrFailedChapterSummaries:
                current.maintenance.missingOrFailedChapterSummaries.map((item) =>
                  shouldClearAll || targetIdSet.has(item.chapterId)
                    ? {
                        ...item,
                        status: "not_generated",
                        isStale: false,
                        summaryId: null,
                        progressMessage: null,
                      }
                    : item,
                ),
            },
          };
        },
      );

      return { previousChapterSummaryLists, previousSummaryProjection };
    },
    onError: (_error, _chapterIds, context) => {
      context?.previousChapterSummaryLists.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
      queryClient.setQueryData(
        getSummaryProjectionQueryKey(projectId),
        context?.previousSummaryProjection,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chapter-summary-list", projectId] });
    },
  });
}

export function useDeleteLongTermSummaries(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ranges: Array<[number, number]>) => deleteLongTermSummaries(projectId, ranges),
    onMutate: async (ranges) => {
      await queryClient.cancelQueries({ queryKey: ["long-term-summaries-page", projectId] });

      const previousLongTermLists = queryClient.getQueriesData<LongTermSummaryListResponse>({
        queryKey: ["long-term-summaries-page", projectId],
      });
      const previousSummaryProjection = queryClient.getQueryData<SummaryProjection>(
        getSummaryProjectionQueryKey(projectId),
      );
      const shouldClearAll = ranges.length === 0;
      const targetRangeSet = new Set(ranges.map(([s, e]) => `${s}-${e}`));

      queryClient.setQueriesData<LongTermSummaryListResponse>(
        { queryKey: ["long-term-summaries-page", projectId] },
        (current) => {
          if (!current) return current;
          const nextItems = shouldClearAll
            ? []
            : current.items.filter(
                (item) => !targetRangeSet.has(`${item.startOrder}-${item.endOrder}`),
              );
          return {
            ...current,
            items: nextItems,
            total: shouldClearAll ? 0 : Math.max(0, current.total - targetRangeSet.size),
          };
        },
      );

      queryClient.setQueryData<SummaryProjection>(
        getSummaryProjectionQueryKey(projectId),
        (current) => {
          if (!current) return current;
          return {
            ...current,
            maintenance: {
              ...current.maintenance,
              missingOrFailedLongTermSummaries:
                current.maintenance.missingOrFailedLongTermSummaries.map((item) =>
                  shouldClearAll || targetRangeSet.has(`${item.startOrder}-${item.endOrder}`)
                    ? {
                        ...item,
                        status: "not_generated",
                        isStale: false,
                        summaryId: null,
                        progressMessage: null,
                      }
                    : item,
                ),
            },
          };
        },
      );

      return { previousLongTermLists, previousSummaryProjection };
    },
    onError: (_error, _ranges, context) => {
      context?.previousLongTermLists.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
      queryClient.setQueryData(
        getSummaryProjectionQueryKey(projectId),
        context?.previousSummaryProjection,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["long-term-summaries-page", projectId] });
    },
  });
}
