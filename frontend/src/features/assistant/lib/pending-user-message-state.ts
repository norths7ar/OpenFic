import type { AgentPendingMessage, AgentPendingMessageAction } from "@/lib/agent.types";

export interface PendingUserMessageEvent {
  action: AgentPendingMessageAction;
  messageId: string;
  content?: string;
  createdAt?: string;
  deliveryMode?: "steer" | "queue";
}

export function createPendingUserMessage(message: AgentPendingMessage): AgentPendingMessage {
  return {
    messageId: message.messageId,
    content: message.content,
    createdAt: message.createdAt,
    deliveryMode: message.deliveryMode,
  };
}

export function applyPendingUserMessageEvent(
  current: AgentPendingMessage | null,
  event: PendingUserMessageEvent,
): AgentPendingMessage | null {
  if (!event.messageId) return current;

  if (event.action === "queued") {
    if (typeof event.content !== "string" || !event.createdAt) return current;
    return createPendingUserMessage({
      messageId: event.messageId,
      content: event.content,
      createdAt: event.createdAt,
      deliveryMode: event.deliveryMode,
    });
  }

  if (current?.messageId !== event.messageId) return current;
  return null;
}
