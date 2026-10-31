import { Box } from "@radix-ui/themes";
import { useCallback, useLayoutEffect, type ReactNode } from "react";
import { Group, Panel, Separator, usePanelCallbackRef, type Layout } from "react-resizable-panels";

import { PanelLayoutLoading } from "@/components/panel-layout-loading";
import { usePersistedPanelLayout } from "@/hooks/use-persisted-panel-layout";

import { useWorkspaceDiscussion } from "../hooks/use-workspace-discussion";
import { WorkspaceDiscussionProvider } from "./workspace-discussion";

import "./workspace-layout.css";

const PANEL_IDS = ["editor", "right-sidebar"];

/** Desktop editor/discussion layout shared by all five editing pages. */
export function WorkspaceLayout({
  children,
  assistant,
}: {
  children: ReactNode;
  assistant: ReactNode;
}) {
  const open = useWorkspaceDiscussion((state) => state.open);
  const layout = usePersistedPanelLayout("panel-layout.project-editor", PANEL_IDS, true);
  const [panel, panelRef] = usePanelCallbackRef();
  useLayoutEffect(() => {
    if (open) panel?.expand();
    else panel?.collapse();
  }, [open, panel]);
  const { onLayoutChanged } = layout;
  const saveLayout = useCallback(
    (next: Layout) => {
      // Persist the expanded width only, never the session's collapsed state.
      if (next["right-sidebar"] > 0) onLayoutChanged(next);
    },
    [onLayoutChanged],
  );

  if (!layout.isLoaded) return <PanelLayoutLoading />;
  return (
    <WorkspaceDiscussionProvider>
      <Group
        orientation="horizontal"
        className="workspace-layout__panels"
        defaultLayout={layout.defaultLayout}
        onLayoutChanged={saveLayout}
      >
        <Panel
          id="editor"
          minSize={30}
        >
          <Box className="workspace-layout__document">{children}</Box>
        </Panel>
        <Separator
          className="workspace-discussion-separator"
          disabled={!open}
          style={open ? undefined : { display: "none" }}
        />
        <Panel
          id="right-sidebar"
          panelRef={panelRef}
          defaultSize={500}
          minSize={300}
          maxSize={600}
          collapsible
          collapsedSize={0}
          onResize={(size, _id, previous) => {
            if (previous && size.inPixels === 0) {
              useWorkspaceDiscussion.setState({ open: false });
            }
          }}
        >
          <Box
            inert={!open}
            className="workspace-layout__discussion"
          >
            {assistant}
          </Box>
        </Panel>
      </Group>
    </WorkspaceDiscussionProvider>
  );
}
