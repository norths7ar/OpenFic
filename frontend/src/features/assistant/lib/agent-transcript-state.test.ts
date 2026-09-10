import { describe, expect, test, vi } from "vite-plus/test";

import type { AgentEvent } from "@/lib/agent.types";

vi.mock("@/i18n", () => ({ default: { t: (key: string) => key } }));

import { applyAgentTranscriptEvent, type AgentTranscriptState } from "./agent-transcript-state";

function state(overrides: Partial<AgentTranscriptState> = {}): AgentTranscriptState {
  return {
    messages: [],
    status: "idle",
    isRunning: false,
    currentStage: "",
    ...overrides,
  };
}

function event(overrides: Partial<AgentEvent>): AgentEvent {
  return {
    type: "text",
    role: "assistant",
    status: "running",
    content: "",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("applyAgentTranscriptEvent", () => {
  test("moves an assistant text event into running state and merges its next delta", () => {
    const first = applyAgentTranscriptEvent(
      state(),
      event({ id: "assistant-1", content: "第一段" }),
      { defaultRunningStage: "写作中" },
    );
    const second = applyAgentTranscriptEvent(
      first.state,
      event({ id: "assistant-1", content: "第二段", payload: { is_delta: true } }),
      { defaultRunningStage: "写作中" },
    );

    expect(first.state).toMatchObject({
      status: "running",
      isRunning: true,
      currentStage: "写作中",
    });
    expect(second.state.messages).toHaveLength(1);
    expect(second.state.messages[0]).toMatchObject({ id: "assistant-1", content: "第一段第二段" });
  });

  test("finishes the transcript and clears the running stage on task completion", () => {
    const running = state({
      status: "running",
      isRunning: true,
      currentStage: "写作中",
      messages: [
        {
          id: "assistant-1",
          type: "text",
          role: "assistant",
          status: "running",
          timestamp: 1,
          content: "草稿",
          isStreaming: true,
        },
      ],
    });
    const result = applyAgentTranscriptEvent(
      running,
      event({
        type: "task_completed",
        status: "completed",
        content: undefined,
        payload: { final_content: "成稿", word_count: 2 },
      }),
    );

    expect(result.state).toMatchObject({ status: "completed", isRunning: false, currentStage: "" });
    expect(result.state.messages[0]).toMatchObject({ isStreaming: false });
    expect(result.message).toMatchObject({ type: "completed", finalContent: "成稿", wordCount: 2 });
  });
});

test("retry reset removes only the failed model draft and ignores its late chunks", () => {
  const first = applyAgentTranscriptEvent(
    state({
      messages: [
        {
          id: "completed-tool",
          type: "tool",
          status: "completed",
          toolResult: { success: true },
          timestamp: 1,
        },
      ],
    }),
    event({
      id: "attempt-a",
      content: "unfinished",
      payload: { is_delta: true, run_id: "attempt-a" },
    }),
  );
  const reset = applyAgentTranscriptEvent(
    first.state,
    event({ type: "attempt_reset", payload: { run_ids: ["attempt-a"] } }),
  );
  expect(reset.state.messages.map((item) => item.id)).toEqual(["completed-tool"]);
  const late = applyAgentTranscriptEvent(
    reset.state,
    event({ id: "attempt-a", content: "late", payload: { is_delta: true, run_id: "attempt-a" } }),
  );
  expect(late.state.messages).toEqual(reset.state.messages);
  const next = applyAgentTranscriptEvent(
    late.state,
    event({
      id: "attempt-b",
      content: "replacement",
      payload: { is_delta: true, run_id: "attempt-b" },
    }),
  );
  expect(next.state.messages.at(-1)?.content).toBe("replacement");
});
