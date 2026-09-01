import type { AssistantSidebarHostRegistration } from "@/app/app-shell-context";

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
    current.replaceComposerWithInitialMarkup === registration.replaceComposerWithInitialMarkup &&
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
