import { Box, Flex, Text } from "@radix-ui/themes";
import { FileText } from "lucide-react";
import type { ReactNode } from "react";

import { EditorTabs } from "@/features/writing/components/editor-tabs";
import { useTabsStore } from "@/features/writing/store/use-tabs-store";

import { WorkspaceDiscussionProvider, WorkspaceDiscussionToggle } from "./workspace-discussion";

export function WorkspaceShell({
  store = useTabsStore,
  emptyLabel,
  children,
  onAddToConversation,
}: {
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
        style={{ height: "100%", minHeight: 0, minWidth: 0, flex: 1 }}
      >
        <EditorTabs
          store={store}
          onAddToConversation={onAddToConversation}
        />
        <Box
          style={{
            flex: 1,
            minHeight: 0,
            position: "relative",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
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
                style={{ flex: 1, minHeight: 0, color: "var(--gray-9)" }}
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
