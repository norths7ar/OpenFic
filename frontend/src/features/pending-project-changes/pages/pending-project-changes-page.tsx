import { Box } from "@radix-ui/themes";
import { useParams } from "react-router";

import { MobileAppSidebarTrigger } from "@/features/app-shell";

import { PendingProjectChangesPanel } from "../components/pending-project-changes-panel";

import "../components/pending-project-changes-dialog.css";
import "./pending-project-changes-page.css";

export function PendingProjectChangesPage() {
  const { projectId = "" } = useParams<{ projectId: string }>();

  return (
    <Box className="pending-project-changes-page">
      <Box className="pending-project-changes-page-mobile-trigger">
        <MobileAppSidebarTrigger />
      </Box>
      <PendingProjectChangesPanel
        projectId={projectId}
        className="pending-project-changes-panel--page"
      />
    </Box>
  );
}
