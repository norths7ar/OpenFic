import { useParams } from "react-router";

import { AssistantSidebarHost } from "@/features/app-shell";

export function DiscussionPage() {
  const { projectId } = useParams<{ projectId: string }>();

  if (!projectId) return null;

  return (
    <AssistantSidebarHost
      projectId={projectId}
      preferredAgentKey="discuss"
      isMobileOverlay={false}
      discussionWorkspace
    />
  );
}
