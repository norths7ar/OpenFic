import { describe, expect, test } from "vite-plus/test";

import { buildPendingInterruptMessages } from "./agent-session-interrupt-state";

const options = { now: () => 10_000 };

describe("buildPendingInterruptMessages", () => {
  test("restores ask_user questions as a pending panel message", () => {
    const questions = [{ title: "方向", description: "选择", options: [{ label: "A" }] }];

    expect(
      buildPendingInterruptMessages(
        [{ interrupt_id: "question-1", type: "ask_user", questions }],
        options,
      ),
    ).toEqual([
      expect.objectContaining({
        id: "question-1",
        type: "question",
        status: "pending",
        questions,
        payload: expect.objectContaining({ action_id: "question-1", questions }),
      }),
    ]);
  });
});
