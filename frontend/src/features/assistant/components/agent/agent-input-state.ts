import type { AgentSessionStatus } from "@/lib/agent.types";

export type AgentInputBodyMode = "composer" | "special_panels";

export interface AgentInputLockState {
  disabled: boolean;
  readOnly?: boolean;
}

export interface AgentInputSendState extends AgentInputLockState {
  hasContent: boolean;
  bodyMode?: AgentInputBodyMode;
}

export function getAgentInputBodyMode(
  agentStatus: AgentSessionStatus | undefined,
  hasSpecialPanels: boolean,
  forceSpecialPanels = false,
): AgentInputBodyMode {
  if (!hasSpecialPanels) return "composer";
  if (forceSpecialPanels) return "special_panels";
  if (agentStatus === "waiting_answer" || agentStatus === "waiting_approval") {
    return "special_panels";
  }
  return "composer";
}

export function isAgentInputLocked({ disabled, readOnly = false }: AgentInputLockState): boolean {
  return disabled || readOnly;
}

export function canSendAgentInput({
  hasContent,
  disabled,
  readOnly = false,
  bodyMode = "composer",
}: AgentInputSendState): boolean {
  if (!hasContent) return false;
  if (disabled || readOnly) return false;
  return bodyMode === "composer";
}
