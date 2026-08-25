import { Box, Container, Flex, Text } from "@radix-ui/themes";
import { FileClock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { MobileAppSidebarTrigger } from "@/features/app-shell";

import { PendingProjectChangesPanel } from "../components/pending-project-changes-panel";

import "../components/pending-project-changes-dialog.css";
import "./pending-project-changes-page.css";

export function PendingProjectChangesPage() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams<{ projectId: string }>();

  return (
    <Box className="pending-project-changes-page">
      <Container
        size="4"
        px="5"
        py="5"
      >
        <Flex
          align="center"
          gap="3"
          mb="2"
        >
          <MobileAppSidebarTrigger />
          <FileClock
            size={24}
            aria-hidden="true"
          />
          <h1 className="pending-project-changes-page-title">{t("pendingProjectChanges.title")}</h1>
        </Flex>
        <Text
          size="2"
          color="gray"
          className="pending-project-changes-page-scope"
        >
          {t("pendingProjectChanges.projectScope")}
        </Text>
        <Box mt="5">
          <PendingProjectChangesPanel projectId={projectId} />
        </Box>
      </Container>
    </Box>
  );
}
