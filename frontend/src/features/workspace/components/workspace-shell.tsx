import "./workspace-shell.css";
import { Box, Flex, Text } from "@radix-ui/themes";
import { FileText } from "lucide-react";
import type { ReactNode } from "react";

import { EditorTabs } from "@/features/writing/components/editor-tabs";
import { useTabsStore } from "@/features/writing/store/use-tabs-store";

import { DocumentTrashButton } from "./document-history";
import { WorkspaceDiscussionProvider, WorkspaceDiscussionToggle } from "./workspace-discussion";

export function WorkspaceShell({
  projectId,
  store = useTabsStore,
  emptyLabel,
  children,
  onAddToConversation,
}: {
  projectId?: string | null;
  store?: typeof useTabsStore;
  emptyLabel: string;
  children: ReactNode;
  onAddToConversation?: (markup: string) => void;
}) {
  const activeTabId = store((s) => s.activeTabId);
  return (
    <WorkspaceDiscussionProvider>
      <Flex
        direction="column"
        className="workspace-shell__root"
      >
        <Flex
          align="center"
          className="workspace-shell__toolbar"
        >
          <Box className="workspace-shell__title">
            <EditorTabs
              store={store}
              onAddToConversation={onAddToConversation}
            />
          </Box>
          {projectId && (
            <Box px="3">
              <DocumentTrashButton projectId={projectId} />
            </Box>
          )}
        </Flex>
        <Box className="workspace-shell__body">
          {activeTabId ? (
            children
          ) : (
            <>
              <Flex
                justify="end"
                py="2"
                px="6"
              >
                <WorkspaceDiscussionToggle />
              </Flex>
              <Flex
                direction="column"
                align="center"
                justify="center"
                gap="3"
                className="workspace-shell__empty-state"
              >
                <FileText
                  size={40}
                  strokeWidth={1.4}
                />
                <Text size="2">{emptyLabel}</Text>
              </Flex>
            </>
          )}
        </Box>
      </Flex>
    </WorkspaceDiscussionProvider>
  );
}
