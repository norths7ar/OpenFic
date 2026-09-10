import NumberFlow from "@number-flow/react";
import { Box, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import {
  ArrowBigDown,
  ArrowBigUp,
  ArrowLeft,
  History,
  Layers2,
  ListChevronsDownUp,
  SquarePen,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { CircularProgress, Spinner } from "@/components";
import type { TokenUsageState } from "@/lib/agent.types";

import { getContextUsagePercent, type SessionTotalUsageState } from "../lib/assistant-usage-state";

import "./assistant-session-header.css";

interface AssistantSessionHeaderProps {
  discussionWorkspace: boolean;
  isViewingSubagent: boolean;
  subagentHeaderLabel: string;
  subagentStatusLabel: string;
  currentTaskTitle: string;
  supportsGlobalScope: boolean;
  contextMode: "global" | "local";
  headerBackLabel: string;
  onBack: () => void;
  onCompact: () => void;
  onHistory: () => void;
  onNewTask: () => void;
  canCompactAgentSession: boolean;
  compactionTooltip: string;
  isCompacting: boolean;
  sessionTotalDisplay: SessionTotalUsageState;
  currentConversationUsage: TokenUsageState;
}

function formatTokenCount(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return String(value);
}

const COST_FORMATTER = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const SMALL_COST_FORMATTER = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

function formatCost(value: number): string {
  return (value < 1 ? SMALL_COST_FORMATTER : COST_FORMATTER).format(value);
}

function formatDetailedCost(value: number): string {
  return String(value);
}

function getAnimatedTokenDisplay(value: number): { value: number; suffix: string } {
  if (value >= 1000000) {
    return {
      value: Number((value / 1000000).toFixed(1)),
      suffix: "M",
    };
  }
  if (value >= 1000) {
    return {
      value: Number((value / 1000).toFixed(1)),
      suffix: "K",
    };
  }
  return { value, suffix: "" };
}

function AnimatedTokenCount({ value }: { value: number }) {
  const display = getAnimatedTokenDisplay(value);

  return (
    <NumberFlow
      value={display.value}
      suffix={display.suffix}
      locales="en-US"
      format={{
        minimumFractionDigits: display.suffix ? 1 : 0,
        maximumFractionDigits: display.suffix ? 1 : 0,
      }}
      className="ai-sidebar-token-number"
    />
  );
}

export function AssistantSessionHeader({
  discussionWorkspace,
  isViewingSubagent,
  subagentHeaderLabel,
  subagentStatusLabel,
  currentTaskTitle,
  supportsGlobalScope,
  contextMode,
  headerBackLabel,
  onBack,
  onCompact,
  onHistory,
  onNewTask,
  canCompactAgentSession,
  compactionTooltip,
  isCompacting,
  sessionTotalDisplay,
  currentConversationUsage,
}: AssistantSessionHeaderProps) {
  const { t } = useTranslation();
  const contextUsagePercent = getContextUsagePercent(currentConversationUsage);
  const contextUsageTooltip = t("assistant.contextUsageTooltip", {
    used: `${formatTokenCount(currentConversationUsage.contextInputTokens)} (${contextUsagePercent.toFixed(1)}%)`,
    total: formatTokenCount(currentConversationUsage.contextLength),
  });

  return (
    <Box className="ai-sidebar-header">
      <Flex
        align="center"
        justify="between"
        gap="2"
        className="ai-sidebar-task-header-row"
      >
        <Flex
          align="center"
          gap="2"
          className="ai-sidebar-task-title-wrap"
        >
          <IconButton
            variant="ghost"
            size="1"
            onClick={onBack}
            aria-label={headerBackLabel}
          >
            <ArrowLeft size={16} />
          </IconButton>
          {isViewingSubagent ? (
            <Flex
              align="center"
              gap="2"
              className="ai-sidebar-task-title-stack"
            >
              <Text
                size="2"
                weight="medium"
                title={subagentHeaderLabel || t("assistant.subagentFallbackTitle")}
                className="ai-sidebar-task-title"
              >
                {subagentHeaderLabel || t("assistant.subagentFallbackTitle")}
              </Text>
              <Text
                size="1"
                color="gray"
                className="ai-sidebar-task-subtitle"
              >
                {subagentStatusLabel}
              </Text>
            </Flex>
          ) : (
            <Flex
              direction="column"
              className="ai-sidebar-task-title-stack"
            >
              <Text
                size="2"
                weight="medium"
                title={currentTaskTitle || t("assistant.taskFallbackTitle")}
                className="ai-sidebar-task-title"
              >
                {currentTaskTitle || t("assistant.taskFallbackTitle")}
              </Text>
              {supportsGlobalScope ? (
                <Text
                  size="1"
                  color="gray"
                  className="ai-sidebar-task-subtitle"
                >
                  {contextMode === "global"
                    ? t("assistant.globalContextLocked")
                    : t("assistant.publicKnowledge")}
                </Text>
              ) : null}
            </Flex>
          )}
        </Flex>

        <Flex
          align="center"
          gap="1"
          className="ai-sidebar-task-actions"
        >
          <Tooltip content={compactionTooltip}>
            <IconButton
              variant="ghost"
              color="gray"
              size="1"
              onClick={onCompact}
              disabled={!canCompactAgentSession}
              aria-label={t("assistant.compactContext")}
              aria-busy={isCompacting || undefined}
            >
              {isCompacting ? <Spinner size={18} /> : <ListChevronsDownUp size={16} />}
            </IconButton>
          </Tooltip>
          {!discussionWorkspace ? (
            <IconButton
              variant="ghost"
              color="gray"
              size="1"
              onClick={onHistory}
              aria-label={t("assistant.history")}
            >
              <History size={16} />
            </IconButton>
          ) : null}
          <IconButton
            variant="ghost"
            color="gray"
            size="1"
            onClick={onNewTask}
            aria-label={t("assistant.newTask")}
          >
            <SquarePen size={16} />
          </IconButton>
        </Flex>
      </Flex>
      <Flex
        align="center"
        justify="between"
        gap="3"
        className="ai-sidebar-token-row"
      >
        <Flex
          align="center"
          gap="2"
          className="ai-sidebar-token-metrics"
        >
          <Text
            size="1"
            weight="medium"
            color="gray"
          >
            {t("assistant.tokens")}
          </Text>
          <Tooltip
            content={t("assistant.totalOutputTokens", {
              count: sessionTotalDisplay.tokenOutput,
            })}
          >
            <Flex
              align="center"
              gap="1"
              className="ai-sidebar-token-metric"
            >
              <ArrowBigUp size={13} />
              <Text
                as="span"
                size="1"
              >
                <AnimatedTokenCount value={sessionTotalDisplay.tokenOutput} />
              </Text>
            </Flex>
          </Tooltip>
          <Tooltip
            content={t("assistant.totalInputTokens", {
              count: sessionTotalDisplay.tokenInput,
            })}
          >
            <Flex
              align="center"
              gap="1"
              className="ai-sidebar-token-metric"
            >
              <ArrowBigDown size={13} />
              <Text
                as="span"
                size="1"
              >
                <AnimatedTokenCount value={sessionTotalDisplay.tokenInput} />
              </Text>
            </Flex>
          </Tooltip>
          <Tooltip content={t("assistant.cachedTokens", { count: sessionTotalDisplay.tokenCache })}>
            <Flex
              align="center"
              gap="1"
              className="ai-sidebar-token-metric"
            >
              <Layers2 size={13} />
              <Text
                as="span"
                size="1"
              >
                <AnimatedTokenCount value={sessionTotalDisplay.tokenCache} />
              </Text>
            </Flex>
          </Tooltip>
        </Flex>
        {sessionTotalDisplay.cost > 0 ? (
          <Tooltip
            content={t("assistant.totalCost", {
              cost: formatDetailedCost(sessionTotalDisplay.cost),
            })}
          >
            <Flex
              align="center"
              className="ai-sidebar-cost ai-sidebar-token-metric"
            >
              <Text
                as="span"
                size="1"
                className="ai-sidebar-token-number"
              >
                $ {formatCost(sessionTotalDisplay.cost)}
              </Text>
            </Flex>
          </Tooltip>
        ) : null}
        <Flex
          align="center"
          className="ai-sidebar-context-wrap"
        >
          <Tooltip content={contextUsageTooltip}>
            <Box
              asChild
              className="ai-sidebar-context-indicator-hitbox"
            >
              <CircularProgress
                value={currentConversationUsage.contextInputTokens}
                max={currentConversationUsage.contextLength}
                size={16}
                strokeWidth={1.75}
                ariaLabel={t("assistant.contextUsage")}
              />
            </Box>
          </Tooltip>
        </Flex>
      </Flex>
    </Box>
  );
}
