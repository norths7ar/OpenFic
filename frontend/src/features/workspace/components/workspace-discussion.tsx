import { IconButton, Tooltip } from "@radix-ui/themes";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useContext, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AppShellContext } from "@/app/app-shell-context";

import { useWorkspaceDiscussion } from "../hooks/use-workspace-discussion";
import { WorkspaceDiscussionContext } from "../hooks/workspace-discussion-context";

export function WorkspaceDiscussionProvider({ children }: { children: ReactNode }) {
  const desktop = useWorkspaceDiscussion();
  const app = useContext(AppShellContext);
  const value = app?.isMobile
    ? {
        open: app.isAssistantSidebarOpen,
        toggle: app.isAssistantSidebarOpen ? app.closeAssistantSidebar : app.openAssistantSidebar,
      }
    : desktop;
  return (
    <WorkspaceDiscussionContext.Provider value={value}>
      {children}
    </WorkspaceDiscussionContext.Provider>
  );
}

export function WorkspaceDiscussionToggle() {
  const discussion = useContext(WorkspaceDiscussionContext);
  const { t } = useTranslation();
  if (!discussion) return null;
  const label = t(
    discussion.open ? "assistant.closeDocumentAssistant" : "assistant.openDocumentAssistant",
  );
  return (
    <Tooltip content={label}>
      <IconButton
        variant="ghost"
        size="2"
        aria-label={label}
        aria-pressed={discussion.open}
        onClick={discussion.toggle}
      >
        {discussion.open ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
      </IconButton>
    </Tooltip>
  );
}
