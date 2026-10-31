import "./clarification-message-card.css";
import { Box, Flex, Text } from "@radix-ui/themes";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { AgentMessage } from "../../../../../../../lib/agent.types";
import { MessageCardShell } from "../../shared/message-shell";
import {
  getClarificationPromptData,
  getClarificationPromptKey,
  type ClarificationAnswerItem,
  type ClarificationPromptData,
} from "./clarification-flow-state";
import {
  ClarificationQuestionActions,
  ClarificationQuestionBody,
} from "./clarification-question-flow";
import { useClarificationQuestionFlow } from "./use-clarification-question-flow";

interface ClarificationMessageCardProps {
  message: Pick<AgentMessage, "questions" | "payload" | "correlationId">;
  onSubmitQuestionAnswer?: (actionId: string, answer: ClarificationAnswerItem[]) => void;
}

export function ClarificationMessageCard({
  message,
  onSubmitQuestionAnswer,
}: ClarificationMessageCardProps) {
  const prompt = getClarificationPromptData(message);

  if (prompt.questions.length === 0) return null;

  return (
    <ClarificationMessageCardContent
      key={getClarificationPromptKey(prompt)}
      prompt={prompt}
      onSubmitQuestionAnswer={onSubmitQuestionAnswer}
    />
  );
}

interface ClarificationMessageCardContentProps {
  prompt: ClarificationPromptData;
  onSubmitQuestionAnswer?: (actionId: string, answer: ClarificationAnswerItem[]) => void;
}

function ClarificationMessageCardContent({
  prompt,
  onSubmitQuestionAnswer,
}: ClarificationMessageCardContentProps) {
  const { t } = useTranslation();
  const model = useClarificationQuestionFlow(prompt, { onSubmitQuestionAnswer });

  return (
    <MessageCardShell>
      <Flex
        align="center"
        gap="2"
        className="clarification-message-card__message"
      >
        <AlertCircle
          size={16}
          className="clarification-message-card__icon"
        />
        <Text
          size="2"
          weight="medium"
          className="clarification-message-card__details"
        >
          {t("assistant.clarificationCardTitle")}
        </Text>
      </Flex>
      <ClarificationQuestionBody
        model={model}
        bodyClassName="agent-question-panel-body"
      />
      {(model.shouldStep || model.canRenderSubmit) && (
        <Box mt="3">
          <ClarificationQuestionActions model={model} />
        </Box>
      )}
    </MessageCardShell>
  );
}
