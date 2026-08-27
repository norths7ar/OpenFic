import i18n from "@/i18n";
import type { AgentMessage } from "@/lib/agent.types";

import { ToolBody, ToolNotice, ToolTextBlock } from "../shared/tool-message-shared";
import {
  asString,
  getStreamingData,
  getToolErrorMessage,
  getToolResultData,
  isRecord,
} from "../shared/tool-message-utils";

function getPendingChange(message: AgentMessage): Record<string, unknown> | null {
  const result = getToolResultData(message);
  if (!isRecord(result)) return null;
  return isRecord(result.pending_change) ? result.pending_change : result;
}

export function ProjectChangeToolMessage({ message }: { message: AgentMessage }) {
  const error = getToolErrorMessage(message);
  const args = getStreamingData(message);
  const change = getPendingChange(message);
  const after = isRecord(change?.after) ? change.after : isRecord(args.after) ? args.after : null;
  const title = asString(after?.title);
  const targetType = asString(change?.target_type) ?? asString(args.target_type);
  const operation = asString(change?.operation) ?? asString(args.operation);

  return (
    <ToolBody>
      <ToolNotice
        title={
          error
            ? i18n.t("assistant.tools.projectChangeFailed")
            : i18n.t("assistant.tools.projectChangeQueued")
        }
        tone={error ? "error" : "neutral"}
      >
        {error ?? i18n.t("assistant.tools.projectChangeQueuedDescription")}
      </ToolNotice>
      <ToolTextBlock
        label={i18n.t("assistant.tools.material")}
        value={title}
      />
      <ToolTextBlock
        label={i18n.t("assistant.tools.targetType")}
        value={targetType}
      />
      <ToolTextBlock
        label={i18n.t("assistant.tools.action")}
        value={operation}
      />
    </ToolBody>
  );
}
