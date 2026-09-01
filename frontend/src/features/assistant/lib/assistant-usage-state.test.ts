import { describe, expect, test } from "vite-plus/test";

import type { TokenUsageState } from "@/lib/agent.types";

import {
  applyTaskUsageDelta,
  applyTaskUsageSnapshot,
  buildTaskConversationUsage,
  createSessionTotalUsageState,
  createTokenUsageState,
  getContextUsagePercent,
  selectConversationUsage,
} from "./assistant-usage-state";

const payload = {
  sessionId: "session-a",
  taskId: "task-a",
  tokenInput: 10,
  tokenOutput: 20,
  tokenCache: 3,
  cost: 0.5,
};

describe("assistant usage state", () => {
  test("creates the expected empty usage states", () => {
    expect(createTokenUsageState(4096)).toEqual({
      tokenInput: 0,
      tokenOutput: 0,
      tokenCache: 0,
      contextInputTokens: 0,
      contextLength: 4096,
    });
    expect(createSessionTotalUsageState("session-a", "task-a")).toEqual({
      sessionId: "session-a",
      taskId: "task-a",
      tokenInput: 0,
      tokenOutput: 0,
      tokenCache: 0,
      cost: 0,
    });
  });

  test("does not let another session's snapshot or delta pollute current totals", () => {
    const current = applyTaskUsageSnapshot(createSessionTotalUsageState(), payload);
    const other = { ...payload, sessionId: "session-b", taskId: "task-b" };

    expect(applyTaskUsageSnapshot(current, other)).toBe(current);
    expect(applyTaskUsageDelta(current, other)).toBe(current);
  });

  test("accumulates usage deltas for the active session", () => {
    const current = applyTaskUsageSnapshot(createSessionTotalUsageState(), payload);
    expect(
      applyTaskUsageDelta(current, { ...payload, tokenInput: 2, tokenOutput: 4, cost: 0.1 }),
    ).toEqual({
      sessionId: "session-a",
      taskId: "task-a",
      tokenInput: 12,
      tokenOutput: 24,
      tokenCache: 6,
      cost: 0.6,
    });
  });

  test("uses stored usage first and subagent usage only as its fallback", () => {
    const stored: TokenUsageState = { ...createTokenUsageState(100), contextInputTokens: 40 };
    const subagent: TokenUsageState = { ...createTokenUsageState(200), contextInputTokens: 80 };

    expect(
      selectConversationUsage({
        usageBySession: { "session-a": stored },
        sessionId: "session-a",
        isSubagent: true,
        subagentUsage: subagent,
      }),
    ).toBe(stored);
    expect(
      selectConversationUsage({
        usageBySession: {},
        sessionId: "session-b",
        isSubagent: true,
        subagentUsage: subagent,
      }),
    ).toBe(subagent);
    expect(
      selectConversationUsage({
        usageBySession: {},
        sessionId: "session-c",
        isSubagent: false,
        subagentUsage: subagent,
        contextLength: 300,
      }),
    ).toEqual(createTokenUsageState(300));
  });

  test("clamps context usage and treats zero context length as empty", () => {
    expect(getContextUsagePercent({ ...createTokenUsageState(0), contextInputTokens: 100 })).toBe(
      0,
    );
    expect(getContextUsagePercent({ ...createTokenUsageState(100), contextInputTokens: -1 })).toBe(
      0,
    );
    expect(getContextUsagePercent({ ...createTokenUsageState(100), contextInputTokens: 150 })).toBe(
      100,
    );
  });

  test("builds conversation usage from a task snapshot", () => {
    expect(buildTaskConversationUsage({ ...payload, contextInputTokens: 30 }, 512)).toEqual({
      tokenInput: 10,
      tokenOutput: 20,
      tokenCache: 3,
      contextInputTokens: 30,
      contextLength: 512,
    });
  });
});
