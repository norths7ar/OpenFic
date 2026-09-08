/**
 * Writing Store
 *
 * 写作状态管理，包含当前章节、侧边栏状态等。
 */

import { create } from "zustand";

import { getPreference, setPreference } from "@/lib/local-db";

const EXPANDED_VOLUME_IDS_KEY = "writing.expandedVolumeIds";
const SIDEBAR_VIEW_KEY = "writing.sidebarView";

interface WritingStore {
  // 当前状态
  currentChapterId: string | null;
  sidebarOpen: boolean;
  expandedVolumeIds: Set<string>;
  hasHydratedExpandedVolumeIds: boolean;
  hasStoredExpandedVolumeIdsPreference: boolean;
  sidebarView: "chapters" | "notes";

  // Actions
  setCurrentChapter: (id: string | null) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  hydrateExpandedVolumeIds: () => Promise<void>;
  setVolumeExpanded: (volumeId: string, expanded: boolean) => void;
  toggleVolumeExpanded: (volumeId: string) => void;
  setSidebarView: (view: "chapters" | "notes") => void;
  hydrateSidebarView: () => Promise<void>;
}

export const useWritingStore = create<WritingStore>((set, get) => ({
  currentChapterId: null,
  sidebarOpen: false,
  expandedVolumeIds: new Set(),
  hasHydratedExpandedVolumeIds: false,
  hasStoredExpandedVolumeIdsPreference: false,
  sidebarView: "chapters",

  setCurrentChapter: (id) => set({ currentChapterId: id }),

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  hydrateExpandedVolumeIds: async () => {
    const rawValue = await getPreference(EXPANDED_VOLUME_IDS_KEY);
    if (!rawValue) {
      set({ hasHydratedExpandedVolumeIds: true });
      return;
    }

    try {
      const ids = JSON.parse(rawValue);
      if (!Array.isArray(ids)) {
        set({ hasHydratedExpandedVolumeIds: true });
        return;
      }
      set({
        expandedVolumeIds: new Set(
          ids.filter((id): id is string => typeof id === "string" && id.length > 0),
        ),
        hasHydratedExpandedVolumeIds: true,
        hasStoredExpandedVolumeIdsPreference: true,
      });
    } catch {
      set({ hasHydratedExpandedVolumeIds: true });
    }
  },

  setVolumeExpanded: (volumeId, expanded) => {
    const next = new Set(get().expandedVolumeIds);
    if (expanded) {
      next.add(volumeId);
    } else {
      next.delete(volumeId);
    }
    set({ expandedVolumeIds: next });
    void setPreference(EXPANDED_VOLUME_IDS_KEY, JSON.stringify([...next]));
  },

  toggleVolumeExpanded: (volumeId) => {
    const isExpanded = get().expandedVolumeIds.has(volumeId);
    get().setVolumeExpanded(volumeId, !isExpanded);
  },

  setSidebarView: (view) => {
    set({ sidebarView: view });
    void setPreference(SIDEBAR_VIEW_KEY, view);
  },

  hydrateSidebarView: async () => {
    const rawValue = await getPreference(SIDEBAR_VIEW_KEY);
    if (rawValue === "notes") {
      set({ sidebarView: "notes" });
    }
  },
}));
