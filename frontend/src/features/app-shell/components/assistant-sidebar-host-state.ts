import type { AssistantSidebarState } from "@/features/assistant/lib/assistant-state.types";
import type { SceneDraftApplyRequest } from "@/features/assistant/lib/scene-draft";

export interface AssistantSidebarHostRegistration {
  id: string;
  host: HTMLElement | null;
  projectId: string;
  isMobileOverlay: boolean;
  isOpen: boolean;
  preferredAgentKey?: string;
  initialComposerMarkup?: string;
  discussionWorkspace?: boolean;
  onStateChange?: (state: AssistantSidebarState) => void;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
  onApplySceneDraft?: (request: SceneDraftApplyRequest) => Promise<boolean>;
  onClose?: () => void;
}

export interface AssistantSidebarHostState extends AssistantSidebarHostRegistration {
  isActive: boolean;
}

export function registerAssistantSidebarHost(
  current: AssistantSidebarHostState | null,
  registration: AssistantSidebarHostRegistration,
): AssistantSidebarHostState {
  if (
    current &&
    current.id === registration.id &&
    current.host === registration.host &&
    current.projectId === registration.projectId &&
    current.isMobileOverlay === registration.isMobileOverlay &&
    current.isOpen === registration.isOpen &&
    current.preferredAgentKey === registration.preferredAgentKey &&
    current.initialComposerMarkup === registration.initialComposerMarkup &&
    current.discussionWorkspace === registration.discussionWorkspace &&
    current.onStateChange === registration.onStateChange &&
    current.onOpenMentionChapter === registration.onOpenMentionChapter &&
    current.onApplySceneDraft === registration.onApplySceneDraft &&
    current.onClose === registration.onClose
  ) {
    return current;
  }
  return { ...registration, isActive: true };
}

export function clearAssistantSidebarHost(
  current: AssistantSidebarHostState | null,
  id: string,
): AssistantSidebarHostState | null {
  if (!current || current.id !== id) return current;
  return { ...current, host: null, isActive: false };
}
