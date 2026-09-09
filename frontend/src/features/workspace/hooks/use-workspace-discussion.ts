import { create } from "zustand";

// Session-only: navigation shares the setting; a reload starts expanded.
export const useWorkspaceDiscussion = create<{ open: boolean; toggle: () => void }>((set) => ({
  open: true,
  toggle: () => set((state) => ({ open: !state.open })),
}));
