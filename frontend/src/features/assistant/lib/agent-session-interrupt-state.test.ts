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

  test("preserves interrupt batch metadata and adds a restored batch id", () => {
    const messages = buildPendingInterruptMessages(
      [
        { id: "a", type: "ask_user" },
        { id: "b", type: "tool_approval", batch_index: 4, batch_total: 9 },
      ],
      options,
    );

    expect(messages).toHaveLength(2);
    expect(messages[0]).toMatchObject({
      interruptBatchId: "restored-interrupt-batch-10000",
      interruptBatchIndex: 0,
      interruptBatchTotal: 2,
    });
    expect(messages[1]).toMatchObject({
      interruptBatchId: "restored-interrupt-batch-10000",
      interruptBatchIndex: 4,
      interruptBatchTotal: 9,
    });
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

  test("uses injected approval copy and safe defaults for malformed input", () => {
    const [custom] = buildPendingInterruptMessages(
      [{ interrupt_id: "custom", type: "tool_approval", tool_name: "run" }],
      { ...options, getApprovalMessage: (toolName) => `批准 ${toolName}` },
    );
    const [defaults] = buildPendingInterruptMessages(
      [
        {
          id: "defaults",
          type: "tool_approval",
          tool_name: "run",
          args: [],
          tool_args: "bad",
          tool_result_preview: [],
          interrupt_behavior: "unknown",
        },
      ],
      options,
    );

    expect(custom.toolApproval?.message).toBe("批准 run");
    expect(defaults.toolApproval).toMatchObject({
      approval_id: "defaults",
      tool_args: {},
      message: "Allow calling run?",
      interrupt_behavior: "cancel",
    });
    expect(defaults.toolApproval?.tool_result_preview).toBeUndefined();
  });

  test("skips missing ids and unknown interrupt types", () => {
    expect(
      buildPendingInterruptMessages(
        [
          { type: "ask_user" },
          { id: "unknown", type: "something_else" },
          { interrupt_id: "known", type: "unknown" },
        ],
        options,
      ),
    ).toEqual([]);
  });

  test("uses the injected clock for batch and message timestamps", () => {
    let current = 700;
    const messages = buildPendingInterruptMessages(
      [
        { id: "a", type: "ask_user" },
        { id: "b", type: "ask_user" },
      ],
      { now: () => current++ },
    );

    expect(messages.map(({ timestamp }) => timestamp)).toEqual([701, 703]);
    expect(messages[0].interruptBatchId).toBe("restored-interrupt-batch-700");
  });
});
