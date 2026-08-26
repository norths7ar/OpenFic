import { Box, Flex, Text } from "@radix-ui/themes";
import { FileText, ListTree } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { AssistantSidebarHost } from "@/features/app-shell";
import type { AssistantSidebarState } from "@/features/assistant";
import { buildNoteMentionTag } from "@/features/assistant/lib/mention-text";
import type { DocumentType } from "@/lib/note.types";

import { NoteEditor } from "../components/note-editor";
import { NoteSidebar } from "../components/note-sidebar";

import "./writing-page.css";

interface DocumentWorkspacePageProps {
  documentType: DocumentType;
}

export function DocumentWorkspacePage({ documentType }: DocumentWorkspacePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useTranslation();
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [selectedTitle, setSelectedTitle] = useState("");
  const [assistantState, setAssistantState] = useState<AssistantSidebarState>({
    agentStatus: "idle",
    isAgentRunning: false,
  });

  const Icon = documentType === "outline" ? ListTree : FileText;
  const emptyLabel = t(
    documentType === "outline" ? "writing.selectOrCreateOutline" : "writing.selectOrCreateNote",
  );

  if (!projectId) return null;

  return (
    <Flex
      className="writing-page-root"
      style={{ minWidth: 0 }}
    >
      <Box
        className="writing-page-sidebar writing-page-sidebar--left"
        style={{ width: 300, minWidth: 260, borderRight: "1px solid var(--gray-a5)" }}
      >
        <NoteSidebar
          projectId={projectId}
          documentType={documentType}
          onNoteSelect={(noteId, title) => {
            setSelectedNoteId(noteId);
            setSelectedTitle(title);
          }}
        />
      </Box>
      <Flex
        direction="column"
        flexGrow="1"
        minWidth="0"
      >
        {selectedNoteId ? (
          <>
            <Flex
              align="center"
              gap="2"
              px="4"
              style={{ height: 48, borderBottom: "1px solid var(--gray-a5)" }}
            >
              <Icon size={18} />
              <Text weight="medium">{selectedTitle}</Text>
            </Flex>
            <Box style={{ flex: 1, minHeight: 0 }}>
              <NoteEditor
                noteId={selectedNoteId}
                projectId={projectId}
                isAgentLocked={assistantState.isAgentRunning}
              />
            </Box>
          </>
        ) : (
          <Flex
            direction="column"
            align="center"
            justify="center"
            gap="3"
            height="100%"
            style={{ color: "var(--gray-9)" }}
          >
            <Icon
              size={40}
              strokeWidth={1.4}
            />
            <Text size="2">{emptyLabel}</Text>
          </Flex>
        )}
      </Flex>
      {selectedNoteId && (
        <Box style={{ width: 420, minWidth: 340, borderLeft: "1px solid var(--gray-a5)" }}>
          <AssistantSidebarHost
            projectId={projectId}
            preferredAgentKey="discuss"
            initialComposerMarkup={buildNoteMentionTag({
              noteId: selectedNoteId,
              label: selectedTitle,
            })}
            onStateChange={setAssistantState}
            isMobileOverlay={false}
          />
        </Box>
      )}
    </Flex>
  );
}
