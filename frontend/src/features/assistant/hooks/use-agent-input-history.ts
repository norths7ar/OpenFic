import { useCallback, useEffect, useRef, useState } from "react";

import {
  getAgentInputHistory,
  registerBrowserBackupFlush,
  setAgentInputHistory,
} from "@/lib/local-db";

import {
  appendAgentInputHistory,
  applyAgentInputChange,
  createAgentInputHistoryState,
  navigateAgentInputHistory,
  normalizeAgentInputDraft,
  type AgentInputHistoryDirection,
  type AgentInputHistoryState,
} from "../lib/agent-input-history-state";

const AGENT_INPUT_DRAFT_SAVE_DELAY = 300;

export function useAgentInputHistory(projectId: string) {
  const [historyState, setHistoryState] = useState<AgentInputHistoryState>(() =>
    createAgentInputHistoryState([]),
  );
  const [draft, setDraft] = useState("");
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null);
  const historyStateRef = useRef(historyState);
  const draftRef = useRef("");
  const draftChangedRef = useRef(false);
  const draftSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const writeQueueRef = useRef(Promise.resolve());

  const commitState = useCallback((nextState: AgentInputHistoryState) => {
    historyStateRef.current = nextState;
    setHistoryState(nextState);
  }, []);

  const persistState = useCallback(
    (targetProjectId: string, entries: string[], targetDraft: string): Promise<void> => {
      if (!targetProjectId) return Promise.resolve();
      const nextWrite = writeQueueRef.current.then(() =>
        setAgentInputHistory(targetProjectId, entries, targetDraft),
      );
      writeQueueRef.current = nextWrite.then(
        () => undefined,
        () => undefined,
      );
      return nextWrite;
    },
    [],
  );

  const clearDraftSaveTimer = useCallback(() => {
    if (draftSaveTimerRef.current === null) return;
    clearTimeout(draftSaveTimerRef.current);
    draftSaveTimerRef.current = null;
  }, []);

  const flushDraftForProject = useCallback(
    (targetProjectId: string): Promise<void> => {
      clearDraftSaveTimer();
      if (!targetProjectId || !draftChangedRef.current) return writeQueueRef.current;
      draftChangedRef.current = false;
      return persistState(targetProjectId, historyStateRef.current.entries, draftRef.current);
    },
    [clearDraftSaveTimer, persistState],
  );

  const scheduleDraftSave = useCallback(
    (value: string) => {
      draftRef.current = normalizeAgentInputDraft(value);
      draftChangedRef.current = true;
      setDraft(draftRef.current);
      clearDraftSaveTimer();
      if (!projectId) return;

      draftSaveTimerRef.current = setTimeout(() => {
        draftSaveTimerRef.current = null;
        if (!draftChangedRef.current) return;
        draftChangedRef.current = false;
        persistState(projectId, historyStateRef.current.entries, draftRef.current);
      }, AGENT_INPUT_DRAFT_SAVE_DELAY);
    },
    [clearDraftSaveTimer, persistState, projectId],
  );

  useEffect(() => {
    let cancelled = false;
    commitState(createAgentInputHistoryState([]));
    draftRef.current = "";
    draftChangedRef.current = false;
    setDraft("");
    setLoadedProjectId(null);

    if (!projectId) {
      setLoadedProjectId(projectId);
      return () => undefined;
    }

    void getAgentInputHistory(projectId).then((storedState) => {
      if (cancelled) return;

      let mergedEntries = storedState.entries;
      for (const entry of historyStateRef.current.entries) {
        mergedEntries = appendAgentInputHistory(mergedEntries, entry);
      }
      const hasPendingDraft = draftChangedRef.current;
      const nextDraft = hasPendingDraft ? draftRef.current : storedState.draft;
      commitState(createAgentInputHistoryState(mergedEntries));
      draftRef.current = nextDraft;
      draftChangedRef.current = false;
      setDraft(nextDraft);
      setLoadedProjectId(projectId);

      if (hasPendingDraft || mergedEntries.length !== storedState.entries.length) {
        persistState(projectId, mergedEntries, nextDraft);
      }
    });

    return () => {
      cancelled = true;
      flushDraftForProject(projectId);
    };
  }, [commitState, flushDraftForProject, persistState, projectId]);

  useEffect(() => {
    const handlePageHide = () => flushDraftForProject(projectId);
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") handlePageHide();
    };

    window.addEventListener("pagehide", handlePageHide);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [flushDraftForProject, projectId]);

  useEffect(
    () => registerBrowserBackupFlush(() => flushDraftForProject(projectId)),
    [flushDraftForProject, projectId],
  );

  const handleInputChange = useCallback(
    (value: string) => {
      commitState(applyAgentInputChange(historyStateRef.current, value));
      scheduleDraftSave(value);
    },
    [commitState, scheduleDraftSave],
  );

  const navigate = useCallback(
    (direction: AgentInputHistoryDirection, currentValue: string): string | null => {
      const result = navigateAgentInputHistory(historyStateRef.current, direction, currentValue);
      if (!result.handled) return null;
      commitState(result.state);
      return result.value;
    },
    [commitState],
  );

  const record = useCallback(
    (value: string) => {
      const currentState = historyStateRef.current;
      const nextEntries = appendAgentInputHistory(currentState.entries, value);
      clearDraftSaveTimer();
      draftRef.current = "";
      draftChangedRef.current = false;
      setDraft("");
      commitState(createAgentInputHistoryState(nextEntries));
      if (projectId) persistState(projectId, nextEntries, "");
    },
    [clearDraftSaveTimer, commitState, persistState, projectId],
  );

  return {
    draft,
    handleInputChange,
    isDraftLoaded: loadedProjectId === projectId,
    navigate,
    record,
    historyState,
  };
}
