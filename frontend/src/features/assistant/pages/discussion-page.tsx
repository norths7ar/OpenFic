import { Box } from "@radix-ui/themes";
import { useParams } from "react-router";

import { AssistantSidebar } from "../components/assistant-sidebar";

export function DiscussionPage() {
  const { projectId } = useParams<{ projectId: string }>();

  if (!projectId) return null;

  return (
    <Box
      height="100%"
      width="100%"
      style={{ maxWidth: 1120, margin: "0 auto", borderInline: "1px solid var(--gray-a5)" }}
    >
      <AssistantSidebar
        projectId={projectId}
        preferredAgentKey="discuss"
      />
    </Box>
  );
}
