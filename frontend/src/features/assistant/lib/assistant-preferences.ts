import type { ReasoningEffort } from "@/lib/agent.types";

export const ASSISTANT_MODEL_STORAGE_KEY = "openfic.agent.selectedModelId";
export const ASSISTANT_AGENT_STORAGE_KEY = "openfic.agent.selectedAgentKey";
export const ASSISTANT_REASONING_EFFORT_STORAGE_KEY = "openfic.agent.reasoningEffort";

const REASONING_EFFORTS: ReasoningEffort[] = ["off", "low", "medium", "high", "xhigh", "max"];

function getStorage(storage?: Storage): Storage | undefined {
  if (storage) return storage;
  if (typeof window === "undefined") return undefined;
  return window.localStorage;
}

function readString(key: string, storage?: Storage): string {
  try {
    return getStorage(storage)?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeString(key: string, value: string, storage?: Storage): void {
  try {
    getStorage(storage)?.setItem(key, value);
  } catch {
    // Local preferences are best effort.
  }
}

export function getStoredModelId(storage?: Storage): string {
  return readString(ASSISTANT_MODEL_STORAGE_KEY, storage);
}

export function storeModelId(modelId: string, storage?: Storage): void {
  if (!modelId) return;
  writeString(ASSISTANT_MODEL_STORAGE_KEY, modelId, storage);
}

export function getStoredAgentKey(storage?: Storage): string {
  return readString(ASSISTANT_AGENT_STORAGE_KEY, storage);
}

export function storeAgentKey(agentKey: string, storage?: Storage): void {
  if (!agentKey) return;
  writeString(ASSISTANT_AGENT_STORAGE_KEY, agentKey, storage);
}

export function isReasoningEffort(value: unknown): value is ReasoningEffort {
  return typeof value === "string" && REASONING_EFFORTS.includes(value as ReasoningEffort);
}

export function getStoredReasoningEffort(
  modelId: string,
  supportsReasoning: boolean,
  storage?: Storage,
): ReasoningEffort {
  if (!supportsReasoning) return "off";
  if (!modelId) return "medium";
  try {
    const stored = JSON.parse(
      getStorage(storage)?.getItem(ASSISTANT_REASONING_EFFORT_STORAGE_KEY) ?? "{}",
    ) as Record<string, unknown>;
    const value = stored[modelId];
    return isReasoningEffort(value) ? value : "medium";
  } catch {
    return "medium";
  }
}

export function storeReasoningEffort(
  modelId: string,
  reasoningEffort: ReasoningEffort,
  storage?: Storage,
): void {
  if (!modelId || !isReasoningEffort(reasoningEffort)) return;
  let stored: Record<string, unknown> = {};
  try {
    stored = JSON.parse(
      getStorage(storage)?.getItem(ASSISTANT_REASONING_EFFORT_STORAGE_KEY) ?? "{}",
    ) as Record<string, unknown>;
  } catch {
    // Replace malformed local preferences with the persisted session value.
  }
  writeString(
    ASSISTANT_REASONING_EFFORT_STORAGE_KEY,
    JSON.stringify({ ...stored, [modelId]: reasoningEffort }),
    storage,
  );
}
