import { Badge, Box, Button, Flex, Text, TextArea } from "@radix-ui/themes";
import { memo } from "react";
import { useTranslation } from "react-i18next";

import type { AgentMessage } from "@/lib/agent.types";

import { AgentMarkdownContent } from "../../../agent-markdown-content";
import { MessageCardShell } from "../../shared/message-shell";

interface AgentOutputMessageProps {
  message: AgentMessage;
  sceneDraft?: {
    content: string;
    status: "active" | "applied" | "discarded";
    onChange: (content: string) => void;
    onApply: () => void;
    onDiscard: () => void;
  };
}

function AgentOutputMessageView({ message, sceneDraft }: AgentOutputMessageProps) {
  const { t } = useTranslation();
  if (sceneDraft) {
    const isActive = sceneDraft.status === "active";
    return (
      <MessageCardShell isStreaming={message.isStreaming || undefined}>
        <Flex
          direction="column"
          gap="3"
          className="agent-output-content"
        >
          <Flex
            align="center"
            justify="between"
          >
            <Text
              size="2"
              weight="medium"
            >
              {t("writing.sceneDraft.previewTitle")}
            </Text>
            {sceneDraft.status !== "active" ? (
              <Badge color={sceneDraft.status === "applied" ? "green" : "gray"}>
                {sceneDraft.status === "applied"
                  ? t("writing.sceneDraft.applied")
                  : t("writing.sceneDraft.discarded")}
              </Badge>
            ) : null}
          </Flex>
          <TextArea
            value={sceneDraft.content}
            onChange={(event) => sceneDraft.onChange(event.target.value)}
            readOnly={!isActive || message.isStreaming}
            rows={14}
            resize="vertical"
          />
          <Text
            size="1"
            color="gray"
          >
            {t("writing.sceneDraft.applyHint")}
          </Text>
          {isActive && !message.isStreaming ? (
            <Flex
              gap="2"
              justify="end"
            >
              <Button
                variant="soft"
                color="gray"
                onClick={sceneDraft.onDiscard}
              >
                {t("writing.sceneDraft.discard")}
              </Button>
              <Button
                onClick={sceneDraft.onApply}
                disabled={!sceneDraft.content.trim()}
              >
                {t("writing.sceneDraft.apply")}
              </Button>
            </Flex>
          ) : null}
        </Flex>
      </MessageCardShell>
    );
  }
  return (
    <MessageCardShell isStreaming={message.isStreaming || undefined}>
      {message.payload?.interrupted === true ? (
        <Text
          as="p"
          size="1"
          color="gray"
        >
          {t("assistant.generationInterrupted")}
        </Text>
      ) : null}
      {message.content ? (
        <Box className="agent-output-content">
          <AgentMarkdownContent
            content={message.content}
            isStreaming={message.isStreaming}
            className="agent-markdown-content"
          />
        </Box>
      ) : null}
    </MessageCardShell>
  );
}

export const AgentOutputMessage = memo(AgentOutputMessageView);
