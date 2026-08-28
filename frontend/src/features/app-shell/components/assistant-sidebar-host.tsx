import { useId, useLayoutEffect, useRef } from "react";

import { useAppShell } from "./app-shell-context";
import type { AssistantSidebarHostRegistration } from "./assistant-sidebar-host-state";

interface AssistantSidebarHostProps extends Omit<
  AssistantSidebarHostRegistration,
  "id" | "host" | "isOpen" | "onClose"
> {
  className?: string;
}

export function AssistantSidebarHost({
  className,
  isMobileOverlay,
  initialComposerMarkup,
  discussionWorkspace,
  onOpenMentionChapter,
  onApplySceneDraft,
  onStateChange,
  preferredAgentKey,
  projectId,
}: AssistantSidebarHostProps) {
  const id = useId();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const {
    clearAssistantSidebarHost,
    closeAssistantSidebar,
    isAssistantSidebarOpen,
    registerAssistantSidebarHost,
  } = useAppShell();
  const callbacksRef = useRef({ onApplySceneDraft, onOpenMentionChapter, onStateChange });
  callbacksRef.current = { onApplySceneDraft, onOpenMentionChapter, onStateChange };

  useLayoutEffect(() => {
    return () => clearAssistantSidebarHost(id);
  }, [clearAssistantSidebarHost, id]);

  useLayoutEffect(() => {
    registerAssistantSidebarHost({
      id,
      host: isMobileOverlay ? null : hostRef.current,
      projectId,
      isMobileOverlay,
      isOpen: isMobileOverlay ? isAssistantSidebarOpen : true,
      preferredAgentKey,
      initialComposerMarkup,
      discussionWorkspace,
      onStateChange: (state) => callbacksRef.current.onStateChange?.(state),
      onOpenMentionChapter: (chapterId, chapterTitle) =>
        callbacksRef.current.onOpenMentionChapter?.(chapterId, chapterTitle),
      onApplySceneDraft: (request) =>
        callbacksRef.current.onApplySceneDraft?.(request) ?? Promise.resolve(false),
      onClose: closeAssistantSidebar,
    });
  }, [
    id,
    isMobileOverlay,
    isAssistantSidebarOpen,
    preferredAgentKey,
    initialComposerMarkup,
    discussionWorkspace,
    projectId,
    closeAssistantSidebar,
    registerAssistantSidebarHost,
  ]);

  if (isMobileOverlay) return null;
  return (
    <div
      ref={hostRef}
      className={
        className
          ? `app-layout-assistant-sidebar-host ${className}`
          : "app-layout-assistant-sidebar-host"
      }
      data-slot="assistant-sidebar-host"
    />
  );
}
