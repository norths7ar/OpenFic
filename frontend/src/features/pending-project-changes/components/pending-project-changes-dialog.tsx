import { Box, Button, Dialog, Flex } from "@radix-ui/themes";
import { FileClock } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { usePendingProjectChangeCount } from "../hooks";
import { PendingProjectChangesPanel } from "./pending-project-changes-panel";

import "./pending-project-changes-dialog.css";

interface PendingProjectChangesDialogProps {
  projectId: string;
}

export function PendingProjectChangesDialog({ projectId }: PendingProjectChangesDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { data } = usePendingProjectChangeCount(projectId);
  const pendingCount = data?.count ?? 0;

  return (
    <>
      <Button
        size="1"
        variant="soft"
        color="amber"
        className="pending-project-changes-trigger"
        onClick={() => setOpen(true)}
      >
        <FileClock size={14} />
        {t("pendingProjectChanges.trigger", { count: pendingCount })}
      </Button>
      <Dialog.Root
        open={open}
        onOpenChange={setOpen}
      >
        <Dialog.Content className="pending-project-changes-dialog-content">
          <Box mb="3">
            <Dialog.Title>{t("pendingProjectChanges.title")}</Dialog.Title>
          </Box>
          <PendingProjectChangesPanel
            projectId={projectId}
            className="pending-project-changes-panel--dialog"
          />
          <Flex
            mt="4"
            justify="end"
          >
            <Dialog.Close>
              <Button
                color="gray"
                variant="soft"
              >
                {t("common.close")}
              </Button>
            </Dialog.Close>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </>
  );
}
