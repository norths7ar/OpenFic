import { describe, expect, test } from "vite-plus/test";

import type { AgentMessage } from "@/lib/agent.types";

import { mergeStreamingMessage } from "./streaming-message-merge";

function message(overrides: Partial<AgentMessage> = {}): AgentMessage {
  return {
    id: "message-1",
    type: "text",
    timestamp: 1_000,
    content: "",
    ...overrides,
  };
}

describe("mergeStreamingMessage", () => {
  test("keeps a completed text body when the terminal event is empty", () => {
    const previous = message({ content: "完整内容", isStreaming: true });
    const completed = message({ content: "", status: "completed" });

    expect(mergeStreamingMessage(previous, completed)).toMatchObject({
      content: "完整内容",
      isStreaming: false,
    });
  });
});
