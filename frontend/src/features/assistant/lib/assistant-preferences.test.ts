import { describe, expect, test } from "vite-plus/test";

import {
  ASSISTANT_AGENT_STORAGE_KEY,
  ASSISTANT_MODEL_STORAGE_KEY,
  ASSISTANT_REASONING_EFFORT_STORAGE_KEY,
  getStoredAgentKey,
  getStoredModelId,
  getStoredReasoningEffort,
  storeAgentKey,
  storeModelId,
  storeReasoningEffort,
} from "./assistant-preferences";

class FakeStorage implements Storage {
  private values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("assistant preferences", () => {
  test("returns SSR-safe defaults and tolerates malformed reasoning JSON", () => {
    const storage = new FakeStorage();

    expect(getStoredModelId()).toBe("");
    expect(getStoredAgentKey()).toBe("");
    expect(getStoredReasoningEffort("model-a", true, storage)).toBe("medium");
    storage.setItem(ASSISTANT_REASONING_EFFORT_STORAGE_KEY, "not-json");
    expect(getStoredReasoningEffort("model-a", true, storage)).toBe("medium");
    expect(getStoredReasoningEffort("model-a", false, storage)).toBe("off");
    expect(getStoredReasoningEffort("", true, storage)).toBe("medium");
  });

  test("accepts every valid reasoning effort and rejects invalid values", () => {
    const storage = new FakeStorage();
    const efforts = ["off", "low", "medium", "high", "xhigh", "max"] as const;

    for (const effort of efforts) {
      storeReasoningEffort("model-a", effort, storage);
      expect(getStoredReasoningEffort("model-a", true, storage)).toBe(effort);
    }
    storage.setItem(ASSISTANT_REASONING_EFFORT_STORAGE_KEY, JSON.stringify({ "model-a": "bad" }));
    expect(getStoredReasoningEffort("model-a", true, storage)).toBe("medium");
  });

  test("keeps reasoning preferences isolated per model", () => {
    const storage = new FakeStorage();

    storeReasoningEffort("model-a", "high", storage);
    storeReasoningEffort("model-b", "low", storage);

    expect(getStoredReasoningEffort("model-a", true, storage)).toBe("high");
    expect(getStoredReasoningEffort("model-b", true, storage)).toBe("low");
  });

  test("writes model and agent preferences under independent keys", () => {
    const storage = new FakeStorage();

    storeModelId("model-a", storage);
    storeAgentKey("build", storage);

    expect(storage.getItem(ASSISTANT_MODEL_STORAGE_KEY)).toBe("model-a");
    expect(storage.getItem(ASSISTANT_AGENT_STORAGE_KEY)).toBe("build");
    expect(getStoredModelId(storage)).toBe("model-a");
    expect(getStoredAgentKey(storage)).toBe("build");
  });
});
