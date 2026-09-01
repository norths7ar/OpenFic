import { describe, expect, test } from "vite-plus/test";

import type { AgentMessage } from "@/lib/agent.types";

import { getReasoningDurationMs, mergeStreamingMessage } from "./streaming-message-merge";

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
  test("appends deltas while preserving the original timestamp and id", () => {
    const previous = message({ content: "先", timestamp: 1_000 });
    const delta = message({
      id: "server-id",
      content: "后",
      timestamp: 2_000,
      status: "running",
      payload: { is_delta: true },
    });

    expect(mergeStreamingMessage(previous, delta)).toMatchObject({
      id: "message-1",
      content: "先后",
      timestamp: 1_000,
      isStreaming: true,
    });
  });

  test("keeps a completed text body when the terminal event is empty", () => {
    const previous = message({ content: "完整内容", isStreaming: true });
    const completed = message({ content: "", status: "completed" });

    expect(mergeStreamingMessage(previous, completed)).toMatchObject({
      content: "完整内容",
      isStreaming: false,
    });
  });

  test("uses persisted duration after reasoning stops and live elapsed time while running", () => {
    const running = message({
      type: "reasoning",
      timestamp: 900,
      status: "running",
      thinkingDurationMs: 50,
    });
    const completed = message({
      type: "reasoning",
      timestamp: 900,
      status: "completed",
      payload: { duration_ms: 120 },
    });

    expect(getReasoningDurationMs(running, 1_000)).toBe(100);
    expect(getReasoningDurationMs(completed, 9_000)).toBe(120);
  });
});
