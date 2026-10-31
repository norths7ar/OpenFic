import "./document-workspace-page.css";
import { Flex, Text } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { useAppShell } from "@/app/app-shell-context";
import { AssistantSidebarHost } from "@/features/app-shell/components/assistant-sidebar-host";
import type { AssistantSidebarState } from "@/features/assistant";
import { buildNoteMentionTag } from "@/features/assistant/lib/mention-text";
import { ProjectNavShell } from "@/features/project-navigation/components/project-nav-shell";
import { WorkspaceLayout } from "@/features/workspace/components/workspace-layout";
import { WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { useWorkspace } from "@/features/workspace/hooks/use-workspace";
import type { DocumentType } from "@/lib/note.types";

import { NoteEditor } from "../components/note-editor";
import { NoteSidebar } from "../components/note-sidebar";
import { useNoteTree } from "../hooks/use-notes";

import "./writing-page.css";

interface DocumentWorkspacePageProps {
  documentType: DocumentType;
}

export function DocumentWorkspacePage({ documentType }: DocumentWorkspacePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useTranslation();
  const workspace = useWorkspace(projectId, documentType);
  const selectedNoteId = workspace.selectedId;
  const selectedTitle = workspace.activeTab?.title ?? "";
  const { data: tree } = useNoteTree(projectId ?? "", documentType);
  useEffect(() => {
    if (!tree || !workspace.ready) return;
    workspace.store
      .getState()
      .syncTabs([...tree.rootNotes, ...tree.categories.flatMap((folder) => folder.notes)], "note");
  }, [tree, workspace.ready, workspace.store]);
  const { isMobile } = useAppShell();
  const [assistantState, setAssistantState] = useState<AssistantSidebarState>({
    agentStatus: "idle",
    isAgentRunning: false,
  });

  const emptyLabel = t(
    documentType === "outline" ? "writing.selectOrCreateOutline" : "writing.selectOrCreateNote",
  );

  if (!projectId) return null;

  const editor = (
    <WorkspaceShell
      projectId={projectId}
      store={workspace.store}
      emptyLabel={emptyLabel}
    >
      <NoteEditor
        noteId={selectedNoteId}
        projectId={projectId}
        scrollTop={workspace.activeTab?.scrollTop ?? 0}
        onScrollPositionChange={(id, top) =>
          workspace.store.getState().updateTabScrollPosition(`note:${id}`, top)
        }
        isAgentLocked={assistantState.isAgentRunning}
      />
    </WorkspaceShell>
  );
  const assistant = selectedNoteId ? (
    <AssistantSidebarHost
      projectId={projectId}
      preferredAgentKey="discuss"
      automaticComposerMarkup={buildNoteMentionTag({
        noteId: selectedNoteId,
        label: selectedTitle,
      })}
      onStateChange={setAssistantState}
      isMobileOverlay={false}
    />
  ) : (
    <Flex
      height="100%"
      align="center"
      justify="center"
      p="4"
    >
      <Text color="gray">{emptyLabel}</Text>
    </Flex>
  );

  return (
    <Flex className="writing-page-root document-workspace-page__workspace">
      <ProjectNavShell>
        <NoteSidebar
          projectId={projectId}
          documentType={documentType}
          selectedNoteId={selectedNoteId}
          onNoteSelect={workspace.select}
        />
      </ProjectNavShell>
      {isMobile ? editor : <WorkspaceLayout assistant={assistant}>{editor}</WorkspaceLayout>}
      {isMobile && (
        <AssistantSidebarHost
          projectId={projectId}
          preferredAgentKey="discuss"
          automaticComposerMarkup={
            selectedNoteId
              ? buildNoteMentionTag({
                  noteId: selectedNoteId,
                  label: selectedTitle,
                })
              : undefined
          }
          onStateChange={setAssistantState}
          isMobileOverlay
        />
      )}
    </Flex>
  );
}
