import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Outlet } from "react-router";

import { AppShellContext, type AssistantSidebarHostRegistration } from "@/app/app-shell-context";
import {
  AssistantSidebar,
  type AssistantSidebarHandle,
} from "@/features/assistant/components/assistant-sidebar";
import type { SceneDraftRequest } from "@/features/assistant/lib/scene-draft";
import { SettingsDialog } from "@/features/settings";
import type { SettingsDialogRoute } from "@/features/settings/lib/settings-route";

import { AppSidebar } from "./app-sidebar";
import {
  clearAssistantSidebarHost as clearAssistantSidebarHostState,
  registerAssistantSidebarHost as registerAssistantSidebarHostState,
  type AssistantSidebarHostState,
} from "./assistant-sidebar-host-state";
import {
  clearAssistantSidebarPosition,
  syncAssistantSidebarPosition,
} from "./assistant-sidebar-position";

import "./app-layout.css";
import { StatusBar } from "./status-bar";

interface AppLayoutProps {
  appearance: "light" | "dark";
  version: string;
  onAppearanceChange: (appearance: "light" | "dark") => void;
}

export function AppLayout({ appearance, version, onAppearanceChange }: AppLayoutProps) {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsRoute, setSettingsRoute] = useState<SettingsDialogRoute | undefined>(undefined);
  const [assistantSidebarHost, setAssistantSidebarHost] =
    useState<AssistantSidebarHostState | null>(null);
  const [isAssistantSidebarOpen, setIsAssistantSidebarOpen] = useState(false);
  const assistantSidebarRef = useRef<AssistantSidebarHandle | null>(null);
  const assistantSidebarContainerRef = useRef<HTMLDivElement | null>(null);
  const assistantSidebarProjectIdRef = useRef<string | null>(null);

  useEffect(() => {
    function handleResize() {
      const nextIsMobile = window.innerWidth < 768;
      setIsMobile(nextIsMobile);

      if (!nextIsMobile) {
        setIsSidebarOpen(false);
      }
    }

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const registerAssistantSidebarHost = useCallback(
    (registration: AssistantSidebarHostRegistration) => {
      setAssistantSidebarHost((current) =>
        registerAssistantSidebarHostState(current, registration),
      );
    },
    [],
  );

  const clearAssistantSidebarHost = useCallback((id: string) => {
    setAssistantSidebarHost((current) => clearAssistantSidebarHostState(current, id));
  }, []);

  const appendToAssistant = useCallback((markup: string) => {
    assistantSidebarRef.current?.appendToComposer(markup);
  }, []);

  const prepareSceneDraft = useCallback((request: SceneDraftRequest) => {
    assistantSidebarRef.current?.prepareSceneDraft(request);
    setIsAssistantSidebarOpen(true);
  }, []);

  const openAssistantSidebar = useCallback(() => setIsAssistantSidebarOpen(true), []);
  const closeAssistantSidebar = useCallback(() => setIsAssistantSidebarOpen(false), []);

  useLayoutEffect(() => {
    const host = assistantSidebarHost?.host;
    if (!host || assistantSidebarHost.isMobileOverlay) {
      const sidebar = assistantSidebarContainerRef.current;
      if (sidebar) clearAssistantSidebarPosition(sidebar);
      return;
    }

    let frameId: number | null = null;
    const updateBounds = () => {
      const sidebar = assistantSidebarContainerRef.current;
      if (!sidebar) return;
      syncAssistantSidebarPosition(sidebar, host);
      if (host.getBoundingClientRect().width > 0 || frameId !== null) return;
      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        const nextSidebar = assistantSidebarContainerRef.current;
        if (nextSidebar) syncAssistantSidebarPosition(nextSidebar, host);
      });
    };
    const resizeObserver = new ResizeObserver(updateBounds);
    resizeObserver.observe(host);
    window.addEventListener("resize", updateBounds);
    updateBounds();
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateBounds);
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, [assistantSidebarHost?.host, assistantSidebarHost?.isMobileOverlay]);

  useLayoutEffect(() => {
    const projectId = assistantSidebarHost?.projectId;
    if (projectId && assistantSidebarProjectIdRef.current !== projectId) {
      if (assistantSidebarProjectIdRef.current) setIsAssistantSidebarOpen(false);
      assistantSidebarProjectIdRef.current = projectId;
    }
  }, [assistantSidebarHost?.projectId]);

  const contextValue = useMemo(
    () => ({
      isMobile,
      isSidebarOpen,
      isSettingsOpen,
      openSidebar: () => setIsSidebarOpen(true),
      closeSidebar: () => setIsSidebarOpen(false),
      toggleSidebar: () => setIsSidebarOpen((prev) => !prev),
      openSettings: (route?: SettingsDialogRoute) => {
        setSettingsRoute(route);
        setIsSettingsOpen(true);
      },
      closeSettings: () => setIsSettingsOpen(false),
      appendToAssistant,
      prepareSceneDraft,
      isAssistantSidebarOpen,
      openAssistantSidebar,
      closeAssistantSidebar,
      registerAssistantSidebarHost,
      clearAssistantSidebarHost,
    }),
    [
      appendToAssistant,
      prepareSceneDraft,
      closeAssistantSidebar,
      clearAssistantSidebarHost,
      isAssistantSidebarOpen,
      isMobile,
      isSettingsOpen,
      isSidebarOpen,
      openAssistantSidebar,
      registerAssistantSidebarHost,
    ],
  );

  const isAssistantSidebarVisible = Boolean(assistantSidebarHost?.isActive);

  return (
    <AppShellContext.Provider value={contextValue}>
      <div className="app-layout-root">
        <div className="app-layout-body">
          <AppSidebar />

          <div className="app-layout-content">
            <Outlet />
          </div>
          {assistantSidebarHost ? (
            <div
              ref={assistantSidebarContainerRef}
              className="app-layout-assistant-sidebar"
              data-active={isAssistantSidebarVisible}
              data-mobile-overlay={String(assistantSidebarHost.isMobileOverlay)}
              data-open={String(assistantSidebarHost.isOpen)}
              inert={!isAssistantSidebarVisible || !assistantSidebarHost.isOpen}
              aria-hidden={!isAssistantSidebarVisible || !assistantSidebarHost.isOpen}
            >
              <AssistantSidebar
                key={assistantSidebarHost.projectId}
                ref={assistantSidebarRef}
                projectId={assistantSidebarHost.projectId}
                preferredAgentKey={assistantSidebarHost.preferredAgentKey}
                initialComposerMarkup={assistantSidebarHost.initialComposerMarkup}
                replaceComposerWithInitialMarkup={
                  assistantSidebarHost.replaceComposerWithInitialMarkup
                }
                discussionWorkspace={assistantSidebarHost.discussionWorkspace}
                onStateChange={
                  assistantSidebarHost.isActive ? assistantSidebarHost.onStateChange : undefined
                }
                onOpenMentionChapter={
                  assistantSidebarHost.isActive
                    ? assistantSidebarHost.onOpenMentionChapter
                    : undefined
                }
                onApplySceneDraft={
                  assistantSidebarHost.isActive ? assistantSidebarHost.onApplySceneDraft : undefined
                }
                onClose={assistantSidebarHost.isActive ? assistantSidebarHost.onClose : undefined}
                isMobileOverlay={assistantSidebarHost.isMobileOverlay}
              />
            </div>
          ) : null}
        </div>

        <StatusBar version={version} />

        <SettingsDialog
          appearance={appearance}
          onAppearanceChange={onAppearanceChange}
          open={isSettingsOpen}
          onOpenChange={setIsSettingsOpen}
          route={settingsRoute}
        />
      </div>
    </AppShellContext.Provider>
  );
}
