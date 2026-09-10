import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useSummaryPanel } from "@/features/writing/hooks/use-summaries";
import { useVolumeTree } from "@/features/writing/hooks/use-volumes";

const CONTEXT_MID_FIELD_CHAPTER_COUNT = 10;
const CONTEXT_NEAR_FIELD_CHAPTER_COUNT = 9;

function needsContextCompletionWarning(status: string, isStale: boolean): boolean {
  if (status === "ready" && !isStale) return false;
  return (
    status === "not_generated" || status === "failed" || status === "queued" || status === "running"
  );
}

export function useSummarySendGuard(
  projectId: string,
  hasContent: boolean,
  performSend: () => void,
) {
  const { data: chaptersData } = useVolumeTree(projectId);
  const { data: summaryPanelData } = useSummaryPanel(projectId);
  const [summaryWarningOpen, setSummaryWarningOpen] = useState(false);
  const pendingSendActionRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setSummaryWarningOpen(false);
      pendingSendActionRef.current = null;
    });
    return () => {
      cancelled = true;
    };
  }, [projectId]);
  const latestChapterOrder = useMemo(
    () =>
      Math.max(
        0,
        ...(chaptersData?.volumes ?? []).flatMap((volume) =>
          volume.chapters.map((chapter) => chapter.order),
        ),
      ),
    [chaptersData?.volumes],
  );

  const hasIncompleteContextSummaries = useMemo(() => {
    const maintenance = summaryPanelData?.maintenance;
    if (!maintenance || latestChapterOrder <= 0) return false;

    const midStartOrder = Math.max(
      1,
      latestChapterOrder - CONTEXT_NEAR_FIELD_CHAPTER_COUNT - CONTEXT_MID_FIELD_CHAPTER_COUNT,
    );
    const midEndOrder = latestChapterOrder - CONTEXT_NEAR_FIELD_CHAPTER_COUNT - 1;
    const hasIncompleteMidSummaries =
      midEndOrder >= midStartOrder &&
      maintenance.missingOrFailedChapterSummaries.some((item) => {
        if (!needsContextCompletionWarning(item.status, item.isStale)) return false;
        return item.chapterOrder >= midStartOrder && item.chapterOrder <= midEndOrder;
      });

    const farMaxEndOrder =
      latestChapterOrder - CONTEXT_NEAR_FIELD_CHAPTER_COUNT - CONTEXT_MID_FIELD_CHAPTER_COUNT - 1;
    const hasIncompleteFarSummaries =
      farMaxEndOrder >= 1 &&
      maintenance.missingOrFailedLongTermSummaries.some((item) => {
        if (!needsContextCompletionWarning(item.status, item.isStale)) return false;
        return item.endOrder <= farMaxEndOrder;
      });

    return hasIncompleteMidSummaries || hasIncompleteFarSummaries;
  }, [latestChapterOrder, summaryPanelData?.maintenance]);

  const handleSend = useCallback(() => {
    if (!hasContent) return;
    if (!hasIncompleteContextSummaries) {
      performSend();
      return;
    }

    pendingSendActionRef.current = performSend;
    setSummaryWarningOpen(true);
  }, [hasIncompleteContextSummaries, hasContent, performSend]);

  const handleConfirmSummaryWarning = useCallback(() => {
    setSummaryWarningOpen(false);
    const action = pendingSendActionRef.current;
    pendingSendActionRef.current = null;
    action?.();
  }, []);

  const handleSummaryWarningOpenChange = useCallback((open: boolean) => {
    setSummaryWarningOpen(open);
    if (!open) pendingSendActionRef.current = null;
  }, []);

  return {
    summaryWarningOpen,
    handleSend,
    handleConfirmSummaryWarning,
    handleSummaryWarningOpenChange,
  };
}
