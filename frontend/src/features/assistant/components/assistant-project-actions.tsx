import { Button, DropdownMenu, Flex } from "@radix-ui/themes";
import { ChevronDown, FileClock, MessageCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import "./assistant-project-actions.css";

interface AssistantProjectActionsProps {
  projectId: string;
  hasAgents: boolean;
  discussionWorkspace: boolean;
  pendingCount: number;
  contextMode: "global" | "local";
  scopeChangeDisabled: boolean;
  supportsGlobalScope: boolean;
  hasActiveSession: boolean;
  onKnowledgeScopeChange: (scope: "global" | "local") => Promise<void>;
}
export function AssistantProjectActions({
  projectId,
  hasAgents,
  discussionWorkspace,
  pendingCount,
  contextMode,
  scopeChangeDisabled,
  supportsGlobalScope,
  hasActiveSession,
  onKnowledgeScopeChange,
}: AssistantProjectActionsProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Flex
      align="center"
      gap="2"
      className="ai-sidebar-project-actions"
    >
      {hasAgents ? (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <Button
              size="1"
              variant="soft"
              color="purple"
              disabled={scopeChangeDisabled}
              aria-label={t("assistant.knowledgeScope")}
            >
              <MessageCircle size={14} />
              {contextMode === "global"
                ? t("assistant.globalKnowledge")
                : t("assistant.publicKnowledge")}
              <ChevronDown size={13} />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Label>{t("assistant.knowledgeScope")}</DropdownMenu.Label>
            <DropdownMenu.Item
              disabled={!supportsGlobalScope}
              onClick={() => void onKnowledgeScopeChange("global")}
            >
              {t("assistant.globalKnowledge")}
            </DropdownMenu.Item>
            <DropdownMenu.Item
              disabled={hasActiveSession && contextMode === "global"}
              onClick={() => void onKnowledgeScopeChange("local")}
            >
              {t("assistant.publicKnowledge")}
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      ) : null}
      {!discussionWorkspace && pendingCount > 0 ? (
        <Button
          size="1"
          variant="soft"
          color="amber"
          className="ai-sidebar-pending-changes"
          onClick={() => navigate(`/projects/${projectId}/changes`)}
        >
          <FileClock size={14} />
          {t("pendingProjectChanges.trigger", { count: pendingCount })}
        </Button>
      ) : null}
    </Flex>
  );
}
