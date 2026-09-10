import { describe, expect, it, vi } from "vitest";
vi.mock("@/i18n", () => ({ default: { t: (key: string) => key } }));
import type { AgentMessage } from "@/lib/agent.types";

import { getProjectChangeSummary, getProjectChangeDetail } from "./project-change-summary";
const message = (extra: Partial<AgentMessage>): AgentMessage => ({
  id: "call",
  type: "tool",
  timestamp: 1,
  toolName: "propose_project_update",
  ...extra,
});
describe("proposal summary", () => {
  it("uses compact tool receipts without requiring full document snapshots", () => {
    const summary = getProjectChangeSummary(
      message({
        toolResult: {
          data: {
            pending_change: {
              id: "compact",
              target_type: "note",
              document_type: "outline",
              title: "第18卷",
              changed_fields: ["body"],
              operation: "update",
            },
          },
        },
      }),
    );
    expect(summary.title).toBe("第18卷");
    expect(summary.material).toBe("outline");
    expect(summary.fields).toEqual(["body"]);
  });
  it("gets existing title and actual changed fields from snapshots", () => {
    const summary = getProjectChangeSummary(
      message({
        toolArgs: { target_type: "character", title: null },
        toolResult: {
          data: {
            pending_change: {
              id: "proposal",
              target_type: "character",
              operation: "update",
              before: { title: "天衡至尊", body: "old", agent_visibility: "public" },
              after: { title: "天衡至尊", body: "new", agent_visibility: "public" },
            },
          },
        },
      }),
    );
    expect(summary.title).toBe("天衡至尊");
    expect(summary.fields).toEqual(["body"]);
    expect(summary.material).toBe("character");
  });
  it("distinguishes outlines and labels raw types", () => {
    expect(
      getProjectChangeSummary(
        message({ toolArgs: { target_type: "note", document_type: "outline" } }),
      ).material,
    ).toBe("outline");
    expect(getProjectChangeDetail(message({ toolArgs: { target_type: "world_entry" } }))).toBe(
      "pendingProjectChanges.materialTypes.worldEntry",
    );
  });
  it("does not infer submission from partial arguments", () => {
    expect(
      getProjectChangeSummary(
        message({ status: "running", partialToolArgs: { target_type: "note", title: "draft" } }),
      ).change,
    ).toBeNull();
  });
  it("shows deleted document titles from before snapshot", () => {
    expect(
      getProjectChangeSummary(
        message({
          toolName: "propose_project_delete",
          toolResult: { data: { pending_change: { before: { title: "Old" }, after: null } } },
        }),
      ).title,
    ).toBe("Old");
  });
});
