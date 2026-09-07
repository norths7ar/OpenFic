import { memo } from "react";
import type { ComponentType } from "react";

import type { RenderableDisplayMessage } from "./display/display-message-types";
import { NodeStartMessage } from "./message-blocks/blocks/node/node-start-message";
import { AgentThinkingMessage } from "./message-blocks/blocks/reasoning/agent-thinking-message";
import { CompactionMessage } from "./message-blocks/blocks/status/compaction-message";
import { CompletedMessage } from "./message-blocks/blocks/status/completed-message";
import { ErrorMessage } from "./message-blocks/blocks/status/error-message";
import { RetryMessage } from "./message-blocks/blocks/status/retry-message";
import { AgentOutputMessage } from "./message-blocks/messages/special/agent-output-message";
import { ToolMessage } from "./message-blocks/messages/tool/tool-message";
import { UserRequestMessage } from "./message-blocks/messages/user/user-request-message";
import { AskUserToolMessage } from "./message-blocks/tools/ask-user/ask-user-tool-message";
import { getAskUserQuestionAnswerPairs } from "./message-blocks/tools/shared/tool-message-utils";

interface AgentMessageRendererProps {
  message: RenderableDisplayMessage;
  nodeStartedAt?: number;
  nodeEndedAt?: number;
  nodeElapsedBaseMs?: number;
  isNodeCollapsed?: boolean;
  onToggleNode?: () => void;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
  onAbortRetry?: () => void;
  sceneDraft?: {
    content: string;
    status: "active" | "applied" | "discarded";
    onChange: (content: string) => void;
    onApply: () => void;
    onDiscard: () => void;
  };
}

interface AgentMessageComponentProps {
  message: RenderableDisplayMessage;
  onAbort?: () => void;
}

const messageComponentMap: Partial<
  Record<RenderableDisplayMessage["type"], ComponentType<AgentMessageComponentProps>>
> = {
  reasoning: AgentThinkingMessage,
  retry: RetryMessage,
  compaction: CompactionMessage,
  completed: CompletedMessage,
  error: ErrorMessage,
  agent_output: AgentOutputMessage,
};

function AgentMessageRendererView({
  message,
  nodeStartedAt,
  nodeEndedAt,
  nodeElapsedBaseMs,
  isNodeCollapsed,
  onToggleNode,
  onOpenMentionChapter,
  onAbortRetry,
  sceneDraft,
}: AgentMessageRendererProps) {
  if (message.type === "node_start") {
    return (
      <NodeStartMessage
        message={message}
        startedAt={nodeStartedAt}
        endedAt={nodeEndedAt}
        elapsedBaseMs={nodeElapsedBaseMs}
        isCollapsed={isNodeCollapsed}
        onToggle={onToggleNode}
      />
    );
  }

  if (message.type === "user_request") {
    return (
      <UserRequestMessage
        message={message}
        onOpenMentionChapter={onOpenMentionChapter}
      />
    );
  }

  if (message.type === "agent_output") {
    return (
      <AgentOutputMessage
        message={message}
        sceneDraft={sceneDraft}
      />
    );
  }

  if (message.type === "tool") {
    if (
      message.toolName === "ask_user" &&
      message.status === "completed" &&
      getAskUserQuestionAnswerPairs(message).length > 0
    ) {
      return <AskUserToolMessage message={message} />;
    }
    return <ToolMessage message={message} />;
  }

  const MessageComponent = messageComponentMap[message.type];
  if (!MessageComponent) return null;

  return (
    <MessageComponent
      message={message}
      onAbort={onAbortRetry}
    />
  );
}

function areAgentMessageRendererPropsEqual(
  prev: AgentMessageRendererProps,
  next: AgentMessageRendererProps,
) {
  return (
    prev.message === next.message &&
    prev.nodeStartedAt === next.nodeStartedAt &&
    prev.nodeEndedAt === next.nodeEndedAt &&
    prev.nodeElapsedBaseMs === next.nodeElapsedBaseMs &&
    prev.isNodeCollapsed === next.isNodeCollapsed &&
    Boolean(prev.onToggleNode) === Boolean(next.onToggleNode) &&
    prev.onOpenMentionChapter === next.onOpenMentionChapter &&
    prev.onAbortRetry === next.onAbortRetry &&
    prev.sceneDraft === next.sceneDraft
  );
}

export const AgentMessageRenderer = memo(
  AgentMessageRendererView,
  areAgentMessageRendererPropsEqual,
);
