import { useCallback, useEffect, useMemo } from "react";

import { createTabsStore } from "@/features/writing/store/use-tabs-store";

export function useWorkspace(projectId: string | null | undefined, page: string) {
  const store = useMemo(() => createTabsStore(), []);
  const state = store();
  const key = projectId ? `workspace:${page}:${projectId}` : null;
  useEffect(() => {
    if (key) void store.getState().setCurrentProject(key);
  }, [key, store]);
  const ready = state.isLoaded && state.currentProjectId === key;
  const activeTab = ready ? state.tabs.find((tab) => tab.id === state.activeTabId) : undefined;
  const select = useCallback(
    (id: string | null, title = "") => {
      if (id) store.getState().openTab(id, title, "note");
      else store.getState().setActiveTab(null);
    },
    [store],
  );
  return {
    store,
    ready,
    tabs: state.tabs,
    activeTab,
    selectedId: activeTab?.refId ?? null,
    select,
  };
}
