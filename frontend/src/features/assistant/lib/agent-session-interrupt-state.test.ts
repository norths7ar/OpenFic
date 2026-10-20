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

  test("normalizes tool approval args, preview, id, and behavior", () => {
    const [message] = buildPendingInterruptMessages(
      [
        {
          id: "interrupt-1",
          type: "tool_approval",
          approval_id: "approval-1",
          tool_name: "write_file",
          tool_args: { path: "draft.md" },
          tool_result_preview: { changed: true },
          tool_call_id: "call-1",
          interrupt_behavior: "block",
          message: "确认写入？",
        },
      ],
      options,
    );

    expect(message).toMatchObject({
      type: "approval",
      toolApproval: {
        approval_id: "approval-1",
        tool_name: "write_file",
        tool_args: { path: "draft.md" },
        tool_result_preview: { changed: true },
        tool_call_id: "call-1",
        message: "确认写入？",
        interrupt_behavior: "block",
      },
    });
  });

});
