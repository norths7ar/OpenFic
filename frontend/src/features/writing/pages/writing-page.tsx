import { Box, Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { List, MessageSquareQuote } from "lucide-react";
import { motion } from "motion/react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { useAppShell } from "@/app/app-shell-context";
import { PanelLayoutLoading } from "@/components";
import { AssistantSidebarHost } from "@/features/app-shell/components/assistant-sidebar-host";

import "./writing-page.css";

import { MobileAppSidebarTrigger } from "@/features/app-shell/components/mobile-app-sidebar-trigger";
import type { AssistantSidebarState } from "@/features/assistant";
import type { SceneDraftApplyRequest } from "@/features/assistant";
import { ProjectNavShell } from "@/features/project-navigation/components/project-nav-shell";
import { WorkspaceLayout } from "@/features/workspace/components/workspace-layout";
import { WorkspaceShell } from "@/features/workspace/components/workspace-shell";

import { ChapterEditor } from "../components/chapter-editor";
import { NoteEditor } from "../components/note-editor";
import { PageLoadingOverlay } from "../components/page-loading-overlay";
import { WritingSidebar } from "../components/writing-sidebar";
import { useNoteTree } from "../hooks/use-notes";
import { useVolumeTree } from "../hooks/use-volumes";
import { isEmptyTab } from "../lib/tab.types";
import { useTabsStore, useActiveTabId, useTabs, useTabsLoaded } from "../store/use-tabs-store";
import { useWritingStore } from "../store/use-writing-store";

const MotionBox = motion.create(Box);
const MOBILE_SIDEBAR_WIDTH = 320;
const SummaryPanel = lazy(() =>
  import("../components/summary-panel").then((module) => ({ default: module.SummaryPanel })),
);

type WritingWorkspaceView = "discuss" | "notes" | "write";

interface WritingPageProps {
  workspaceView?: WritingWorkspaceView;
}

export function WritingPage({ workspaceView = "write" }: WritingPageProps) {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  const {
    appendToAssistant,
    isAssistantSidebarOpen,
    isMobile,
    openAssistantSidebar,
    prepareSceneDraft,
  } = useAppShell();

  const { setCurrentChapter, hydrateSidebarView, setSidebarView } = useWritingStore();
  const { openTab, syncTabsWithChapters, syncTabs, setCurrentProject, updateTabScrollPosition } =
    useTabsStore();
  const activeTabId = useActiveTabId();
  const tabs = useTabs();
  const isTabsLoaded = useTabsLoaded();

  const activeTab = useMemo(() => tabs.find((t) => t.id === activeTabId), [tabs, activeTabId]);
  const activeRefId = useMemo(() => activeTab?.refId ?? null, [activeTab]);
  const activeType = useMemo(() => activeTab?.type ?? "chapter", [activeTab]);

  const currentChapterId = useMemo(
    () => (activeTab?.type === "chapter" ? activeTab.refId : null),
    [activeTab],
  );
  const activeEditorScrollTop = activeTab?.scrollTop ?? 0;

  const { data: chaptersData, isLoading: isChaptersLoading } = useVolumeTree(projectId ?? "");

  const { data: noteTreeData } = useNoteTree(projectId ?? "");

  const isPageLoading = !isTabsLoaded || isChaptersLoading;

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSummaryOpen, setIsSummaryOpen] = useState(false);
  const [hasOpenedSummary, setHasOpenedSummary] = useState(false);
  const [hasEditorSelection, setHasEditorSelection] = useState(false);
  const addSelectionToConversationRef = useRef<(() => void) | null>(null);
  const applySceneDraftRef = useRef<((request: SceneDraftApplyRequest) => Promise<boolean>) | null>(
    null,
  );
  const [assistantState, setAssistantState] = useState<AssistantSidebarState>({
    agentStatus: "idle",
    isAgentRunning: false,
  });

  const isAgentLocked = useMemo(
    () => assistantState.isAgentRunning,
    [assistantState.isAgentRunning],
  );
  const isViewingSubagent = assistantState.conversationDescriptor?.kind === "subagent";
  const handleApplySceneDraft = useCallback(async (request: SceneDraftApplyRequest) => {
    return (await applySceneDraftRef.current?.(request)) ?? false;
  }, []);

  useEffect(() => {
    let cancelled = false;
    void hydrateSidebarView().then(() => {
      if (cancelled) return;
      if (workspaceView === "notes") setSidebarView("notes");
      if (workspaceView === "write") setSidebarView("chapters");
    });
    if (workspaceView === "discuss") openAssistantSidebar();
    return () => {
      cancelled = true;
    };
  }, [hydrateSidebarView, openAssistantSidebar, setSidebarView, workspaceView]);

  const allChapters = useMemo(
    () => chaptersData?.volumes.flatMap((volume) => volume.chapters) ?? [],
    [chaptersData],
  );

  const allNotes = useMemo(() => {
    if (!noteTreeData) return [];
    const notes: { id: string; title: string }[] = [];
    const walk = (categories: typeof noteTreeData.categories) => {
      for (const cat of categories) {
        for (const n of cat.notes) {
          notes.push({ id: n.id, title: n.title });
        }
        walk(cat.categories);
      }
    };
    walk(noteTreeData.categories);
    for (const n of noteTreeData.rootNotes) {
      notes.push({ id: n.id, title: n.title });
    }
    return notes;
  }, [noteTreeData]);

  const initialChapterNavigationSequenceRef = useRef(0);
  const prevProjectIdRef = useRef<string | null>(null);
  const [initialCurrentChapterNavigationKey, setInitialCurrentChapterNavigationKey] = useState<
    string | null
  >(null);

  useEffect(() => {
    if (!projectId) return;

    if (prevProjectIdRef.current !== projectId) {
      prevProjectIdRef.current = projectId;
      initialChapterNavigationSequenceRef.current += 1;
      setInitialCurrentChapterNavigationKey(
        `${projectId}:${initialChapterNavigationSequenceRef.current}`,
      );
    }

    const loadProject = async () => {
      await setCurrentProject(projectId);
    };

    loadProject();
  }, [projectId, setCurrentProject]);

  useEffect(() => {
    if (!isTabsLoaded || isChaptersLoading || !chaptersData) return;
    syncTabsWithChapters(allChapters);
  }, [allChapters, chaptersData, isChaptersLoading, syncTabsWithChapters, isTabsLoaded]);

  useEffect(() => {
    if (!isTabsLoaded || !noteTreeData) return;
    syncTabs(allNotes, "note");
  }, [allNotes, noteTreeData, syncTabs, isTabsLoaded]);

  useEffect(() => {
    setCurrentChapter(currentChapterId);
  }, [currentChapterId, setCurrentChapter]);

  useEffect(() => {
    if (!isMobile || !currentChapterId) return;

    const frameId = window.requestAnimationFrame(() => {
      const activeElement = document.activeElement;
      if (!(activeElement instanceof HTMLElement)) return;

      const isTextInput =
        activeElement instanceof HTMLInputElement || activeElement instanceof HTMLTextAreaElement;

      // Mobile browsers may restore editor/title focus after chapter navigation.
      if (!isTextInput && !activeElement.isContentEditable) return;

      activeElement.blur();
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [currentChapterId, isMobile]);

  const handleSelectItem = useCallback(
    (refId: string, title: string, type: "chapter" | "note" = "chapter") => {
      if (isMobile) setIsSidebarOpen(false);
      openTab(refId, title, type);
    },
    [openTab, isMobile],
  );

  const handleChapterSelect = useCallback(
    (chapterId: string, chapterTitle: string) => {
      handleSelectItem(chapterId, chapterTitle, "chapter");
    },
    [handleSelectItem],
  );

  const handleEditorScrollPositionChange = useCallback(
    (type: "chapter" | "note", entityId: string, scrollTop: number) => {
      updateTabScrollPosition(`${type}:${entityId}`, scrollTop);
    },
    [updateTabScrollPosition],
  );

  const handleChapterScrollPositionChange = useCallback(
    (chapterId: string, scrollTop: number) => {
      handleEditorScrollPositionChange("chapter", chapterId, scrollTop);
    },
    [handleEditorScrollPositionChange],
  );

  const handleNoteScrollPositionChange = useCallback(
    (noteId: string, scrollTop: number) => {
      handleEditorScrollPositionChange("note", noteId, scrollTop);
    },
    [handleEditorScrollPositionChange],
  );

  const handleNoteSelect = useCallback(
    (noteId: string, noteTitle: string) => {
      handleSelectItem(noteId, noteTitle, "note");
    },
    [handleSelectItem],
  );

  const handleAddToConversation = useCallback(
    (markup: string) => {
      if (!markup.trim()) return;

      if (isMobile && !isAssistantSidebarOpen) {
        openAssistantSidebar();
        window.requestAnimationFrame(() => {
          appendToAssistant(markup);
        });
        return;
      }

      appendToAssistant(markup);
    },
    [appendToAssistant, isAssistantSidebarOpen, isMobile, openAssistantSidebar],
  );

  const handleOpenSummary = useCallback(() => {
    setHasOpenedSummary(true);
    setIsSummaryOpen(true);
  }, []);

  const handleSummaryOpenChange = useCallback((open: boolean) => {
    if (open) setHasOpenedSummary(true);
    setIsSummaryOpen(open);
  }, []);

  if (!projectId) {
    return null;
  }

  const sidebarContent = (
    <WritingSidebar
      onOpenSummary={handleOpenSummary}
      projectId={projectId}
      onChapterSelect={handleChapterSelect}
      onNoteSelect={handleNoteSelect}
      isAgentLocked={isAgentLocked}
      onAddToConversation={isViewingSubagent ? undefined : handleAddToConversation}
      initialCurrentChapterNavigationKey={initialCurrentChapterNavigationKey}
      showNotes={false}
    />
  );

  return (
    <Box className="writing-page-root">
      <PageLoadingOverlay isLoading={isMobile && isPageLoading} />

      <Box className="writing-page-shell">
        {!isMobile ? (
          <Flex style={{ height: "100%", minWidth: 0 }}>
            <ProjectNavShell>{sidebarContent}</ProjectNavShell>
            <WorkspaceLayout
              assistant={
                <>
                  <AssistantSidebarHost
                    projectId={projectId}
                    preferredAgentKey={workspaceView === "discuss" ? "discuss" : undefined}
                    onStateChange={setAssistantState}
                    onOpenMentionChapter={handleChapterSelect}
                    onApplySceneDraft={handleApplySceneDraft}
                    isMobileOverlay={false}
                  />
                </>
              }
            >
              <WorkspaceShell
                projectId={projectId}
                emptyLabel="从左侧选择或新建章节"
                onAddToConversation={isViewingSubagent ? undefined : handleAddToConversation}
              >
                <Box className="writing-page-content-fill">
                  {activeTabId && !isEmptyTab(activeTabId) ? (
                    activeType === "note" ? (
                      <NoteEditor
                        noteId={activeRefId}
                        scrollTop={activeEditorScrollTop}
                        projectId={projectId}
                        isAgentLocked={isAgentLocked}
                        onScrollPositionChange={handleNoteScrollPositionChange}
                      />
                    ) : (
                      <ChapterEditor
                        chapterId={activeRefId}
                        scrollTop={activeEditorScrollTop}
                        projectId={projectId}
                        isAgentLocked={isAgentLocked}
                        onScrollPositionChange={handleChapterScrollPositionChange}
                        onAddToConversation={
                          isViewingSubagent ? undefined : handleAddToConversation
                        }
                        onPrepareSceneDraft={prepareSceneDraft}
                        applySceneDraftRef={applySceneDraftRef}
                      />
                    )
                  ) : null}
                </Box>
              </WorkspaceShell>
            </WorkspaceLayout>
          </Flex>
        ) : isMobile ? (
          <Flex className="writing-page-mobile-layout">
            <div className="writing-page-editor-shell writing-page-editor-shell--mobile">
              <Flex
                align="center"
                justify="between"
                px="3"
                py="2"
                className="writing-page-mobile-topbar"
              >
                <Flex
                  align="center"
                  gap="1"
                >
                  <MobileAppSidebarTrigger />
                  <Tooltip content={t("writing.chapters")}>
                    <IconButton
                      variant="ghost"
                      size="2"
                      aria-label={t("writing.chapters")}
                      onClick={() => setIsSidebarOpen((open) => !open)}
                    >
                      <List size={18} />
                    </IconButton>
                  </Tooltip>
                </Flex>

                <Flex
                  align="center"
                  gap="1"
                >
                  {!isViewingSubagent && hasEditorSelection && (
                    <Tooltip content={t("editor.addSelectedToConversation")}>
                      <IconButton
                        variant="ghost"
                        size="2"
                        aria-label={t("editor.addSelectedToConversation")}
                        onClick={() => addSelectionToConversationRef.current?.()}
                      >
                        <MessageSquareQuote size={18} />
                      </IconButton>
                    </Tooltip>
                  )}
                </Flex>
              </Flex>

              <WorkspaceShell
                projectId={projectId}
                emptyLabel="从左侧选择或新建章节"
                onAddToConversation={isViewingSubagent ? undefined : handleAddToConversation}
              >
                {activeTabId && !isEmptyTab(activeTabId) ? (
                  activeType === "note" ? (
                    <NoteEditor
                      noteId={activeRefId}
                      scrollTop={activeEditorScrollTop}
                      projectId={projectId}
                      isAgentLocked={isAgentLocked}
                      onScrollPositionChange={handleNoteScrollPositionChange}
                    />
                  ) : (
                    <ChapterEditor
                      chapterId={activeRefId}
                      scrollTop={activeEditorScrollTop}
                      projectId={projectId}
                      isAgentLocked={isAgentLocked}
                      onScrollPositionChange={handleChapterScrollPositionChange}
                      onAddToConversation={isViewingSubagent ? undefined : handleAddToConversation}
                      onSelectionChange={setHasEditorSelection}
                      addSelectionToConversationRef={addSelectionToConversationRef}
                      onPrepareSceneDraft={prepareSceneDraft}
                      applySceneDraftRef={applySceneDraftRef}
                    />
                  )
                ) : null}
              </WorkspaceShell>

              <motion.div
                initial={false}
                animate={{ opacity: isSidebarOpen ? 1 : 0 }}
                transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                onClick={() => setIsSidebarOpen(false)}
                className="writing-page-mobile-sidebar-backdrop"
                style={{ pointerEvents: isSidebarOpen ? "auto" : "none" }}
              />

              <MotionBox
                initial={false}
                animate={{
                  x: isSidebarOpen ? 0 : -MOBILE_SIDEBAR_WIDTH,
                }}
                transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                className="writing-page-mobile-sidebar-sheet"
                style={{
                  width: MOBILE_SIDEBAR_WIDTH,
                  minWidth: MOBILE_SIDEBAR_WIDTH,
                  pointerEvents: isSidebarOpen ? "auto" : "none",
                }}
              >
                <WritingSidebar
                  onOpenSummary={handleOpenSummary}
                  projectId={projectId}
                  onChapterSelect={handleChapterSelect}
                  onNoteSelect={handleNoteSelect}
                  isAgentLocked={isAgentLocked}
                  onAddToConversation={isViewingSubagent ? undefined : handleAddToConversation}
                  compact
                  initialCurrentChapterNavigationKey={initialCurrentChapterNavigationKey}
                  showNotes={false}
                />
              </MotionBox>
            </div>
          </Flex>
        ) : (
          <PanelLayoutLoading />
        )}
      </Box>

      {isMobile && (
        <AssistantSidebarHost
          projectId={projectId}
          preferredAgentKey={workspaceView === "discuss" ? "discuss" : undefined}
          onStateChange={setAssistantState}
          onOpenMentionChapter={handleChapterSelect}
          onApplySceneDraft={handleApplySceneDraft}
          isMobileOverlay
        />
      )}
      {hasOpenedSummary && (
        <Suspense fallback={null}>
          <SummaryPanel
            projectId={projectId}
            open={isSummaryOpen}
            onOpenChange={handleSummaryOpenChange}
            trigger={null}
          />
        </Suspense>
      )}
    </Box>
  );
}
