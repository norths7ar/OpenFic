import i18n from "@/i18n";
import type { AgentMessage } from "@/lib/agent.types";

import { ToolBody, ToolNotice, ToolTextBlock } from "./tool-message-shared";
import { formatValue, getStreamingData, getToolResultData } from "./tool-message-utils";

interface ToolErrorMessageProps {
  errorMessage: string;
}

interface UnregisteredToolMessageProps {
  toolName?: string;
  errorMessage?: string;
}

interface GenericToolMessageProps {
  message: AgentMessage;
  errorMessage?: string;
}

export function ToolErrorMessage({ errorMessage }: ToolErrorMessageProps) {
  return (
    <ToolBody>
      <ToolNotice
        title={i18n.t("assistant.tools.toolError")}
        tone="error"
      >
        {errorMessage}
      </ToolNotice>
    </ToolBody>
  );
}

export function UnregisteredToolMessage({ toolName, errorMessage }: UnregisteredToolMessageProps) {
  return (
    <ToolBody>
      <ToolNotice
        title={i18n.t("assistant.tools.unregisteredTool")}
        tone="warning"
      >
        {i18n.t("assistant.tools.unregisteredToolDescription")}
      </ToolNotice>
      <ToolTextBlock
        label={i18n.t("assistant.tools.toolName")}
        value={toolName ?? i18n.t("assistant.tools.unknown")}
      />
      <ToolTextBlock
        label={i18n.t("assistant.tools.description")}
        value={errorMessage}
      />
    </ToolBody>
  );
}

export function GenericToolMessage({ message, errorMessage }: GenericToolMessageProps) {
  return (
    <ToolBody>
      {errorMessage ? (
        <ToolNotice
          title={i18n.t("assistant.tools.toolError")}
          tone="error"
        >
          {errorMessage}
        </ToolNotice>
      ) : (
        <ToolNotice title={i18n.t("assistant.tools.genericToolResult")}>
          {i18n.t("assistant.tools.genericToolDescription")}
        </ToolNotice>
      )}
      <ToolTextBlock
        label={i18n.t("assistant.tools.input")}
        value={formatValue(getStreamingData(message))}
      />
      <ToolTextBlock
        label={i18n.t("assistant.tools.output")}
        value={formatValue(getToolResultData(message))}
      />
    </ToolBody>
  );
}
