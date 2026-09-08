import { describe, expect, it } from "vitest";

import { agentVisibilityCatalogSchema } from "./agent-visibility";

const state = (value: string) => ({
  value,
  label: value,
  description: "",
  export_marker: "",
  scopes: ["future-scope"],
});

describe("visibility catalog validation", () => {
  it("accepts dynamic state values, count and scope names without changing order", () => {
    const catalog = {
      states: [state("one"), state("two"), state("three"), state("four")],
      default: "two",
    };
    expect(agentVisibilityCatalogSchema.parse(catalog)).toEqual(catalog);
  });
  it.each([
    null,
    { states: [], default: "one" },
    { states: [state("one"), state("one")], default: "one" },
    { states: [state("one")], default: "missing" },
    { states: [{ ...state("one"), scopes: "local" }], default: "one" },
    { states: [{ ...state("one"), label: null }], default: "one" },
  ])("rejects invalid catalog %j", (value) => {
    expect(agentVisibilityCatalogSchema.safeParse(value).success).toBe(false);
  });
});
