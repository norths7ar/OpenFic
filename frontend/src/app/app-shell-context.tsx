import { createContext, useContext } from "react";

import type { AssistantSidebarState } from "@/features/assistant/lib/assistant-state.types";
import type {
  SceneDraftApplyRequest,
  SceneDraftRequest,
} from "@/features/assistant/lib/scene-draft";
import type { SettingsDialogRoute } from "@/features/settings/lib/settings-route";

export interface AssistantSidebarHostRegistration {
  id: string;
  host: HTMLElement | null;
  projectId: string;
  isMobileOverlay: boolean;
  isOpen: boolean;
  preferredAgentKey?: string;
  initialComposerMarkup?: string;
  replaceComposerWithInitialMarkup?: boolean;
  discussionWorkspace?: boolean;
  onStateChange?: (state: AssistantSidebarState) => void;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
  onApplySceneDraft?: (request: SceneDraftApplyRequest) => Promise<boolean>;
  onClose?: () => void;
}

interface AppShellContextValue {
  isMobile: boolean;
  isSidebarOpen: boolean;
  isSettingsOpen: boolean;
  openSidebar: () => void;
  closeSidebar: () => void;
  toggleSidebar: () => void;
  openSettings: (route?: SettingsDialogRoute) => void;
  closeSettings: () => void;
  appendToAssistant: (markup: string) => void;
  prepareSceneDraft: (request: SceneDraftRequest) => void;
  isAssistantSidebarOpen: boolean;
  openAssistantSidebar: () => void;
  closeAssistantSidebar: () => void;
  registerAssistantSidebarHost: (registration: AssistantSidebarHostRegistration) => void;
  clearAssistantSidebarHost: (id: string) => void;
}

export const AppShellContext = createContext<AppShellContextValue | null>(null);

export function useAppShell(): AppShellContextValue {
  const context = useContext(AppShellContext);

  if (!context) {
    throw new Error("useAppShell must be used within AppLayout");
  }

  return context;
}
