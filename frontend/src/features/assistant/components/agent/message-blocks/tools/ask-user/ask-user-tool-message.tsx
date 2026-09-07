import { Box, Text } from "@radix-ui/themes";

import i18n from "@/i18n";
import type { AgentMessage } from "@/lib/agent.types";

import "./ask-user-tool-message.css";

import { MessageCardShell, UserMessageShell } from "../../shared/message-shell";
import { getAskUserQuestionAnswerPairs } from "../shared/tool-message-utils";

interface AskUserToolMessageProps {
  message: AgentMessage;
}

export function AskUserToolMessage({ message }: AskUserToolMessageProps) {
  if (message.status !== "completed") return null;
  const pairs = getAskUserQuestionAnswerPairs(message);
  if (pairs.length === 0) return null;

  return (
    <Box className="agent-ask-user-responses">
      {pairs.map((pair, index) => (
        <UserMessageShell key={`${pair.question}-${index}`}>
          <MessageCardShell className="ai-sidebar-user-message agent-ask-user-response">
            <Text className="agent-user-message-author">
              {i18n.t("assistant.userMessageLabel")}
            </Text>
            <Text className="agent-ask-user-response-question">
              {i18n.t("assistant.clarification.answerTo", {
                question: pair.description ?? pair.question,
              })}
            </Text>
            <Box className="agent-ask-user-response-value">{pair.answer}</Box>
          </MessageCardShell>
        </UserMessageShell>
      ))}
    </Box>
  );
}
