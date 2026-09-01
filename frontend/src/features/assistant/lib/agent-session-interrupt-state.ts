import type { AgentMessage, ClarificationQuestion } from "@/lib/agent.types";

type InterruptRecord = Record<string, unknown>;

export interface BuildPendingInterruptMessagesOptions {
  now: () => number;
  getApprovalMessage?: (toolName: string) => string;
}

function isRecord(value: unknown): value is InterruptRecord {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function getString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function getDefaultApprovalMessage(toolName: string): string {
  return `Allow calling ${toolName}?`;
}

export function buildPendingInterruptMessages(
  interrupts: InterruptRecord[],
  options: BuildPendingInterruptMessagesOptions,
): AgentMessage[] {
  const restoredBatchId =
    interrupts.length > 1 ? `restored-interrupt-batch-${options.now()}` : undefined;
  return interrupts.flatMap((interrupt, index): AgentMessage[] => {
    const interruptId = getString(interrupt.interrupt_id) || getString(interrupt.id);
    if (!interruptId) return [];
    const timestamp = options.now() + index;
    const batchFields = {
      interruptBatchId: getString(interrupt.batch_id) || restoredBatchId,
      interruptBatchIndex:
        typeof interrupt.batch_index === "number" ? interrupt.batch_index : index,
      interruptBatchTotal:
        typeof interrupt.batch_total === "number" ? interrupt.batch_total : interrupts.length,
    };
    if (interrupt.type === "ask_user") {
      const questions = Array.isArray(interrupt.questions)
        ? (interrupt.questions as ClarificationQuestion[])
        : [];
      return [
        {
          id: interruptId,
          type: "question",
          role: "system",
          status: "pending",
          display: "panel",
          timestamp,
          questions,
          payload: { action_id: interruptId, questions, ...batchFields },
          correlationId: interruptId,
          ...batchFields,
        },
      ];
    }
    if (interrupt.type !== "tool_approval") return [];
    const toolName = getString(interrupt.tool_name) || "";
    const toolArgs = isRecord(interrupt.args)
      ? interrupt.args
      : isRecord(interrupt.tool_args)
        ? interrupt.tool_args
        : {};
    const approvalId = getString(interrupt.approval_id) || interruptId;
    const toolResultPreview = isRecord(interrupt.tool_result_preview)
      ? interrupt.tool_result_preview
      : undefined;
    return [
      {
        id: interruptId,
        type: "approval",
        role: "system",
        status: "pending",
        display: "panel",
        timestamp,
        toolApproval: {
          approval_id: approvalId,
          tool_name: toolName,
          tool_args: toolArgs,
          tool_call_id: getString(interrupt.tool_call_id),
          tool_result_preview: toolResultPreview,
          message:
            getString(interrupt.message) ||
            (options.getApprovalMessage ?? getDefaultApprovalMessage)(toolName),
          interrupt_behavior: interrupt.interrupt_behavior === "block" ? "block" : "cancel",
        },
        payload: {
          approval_id: approvalId,
          tool_name: toolName,
          tool_args: toolArgs,
          tool_call_id: getString(interrupt.tool_call_id),
          tool_result_preview: toolResultPreview,
          ...batchFields,
        },
        correlationId: interruptId,
        ...batchFields,
      },
    ];
  });
}
