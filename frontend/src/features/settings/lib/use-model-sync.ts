import { useQueries, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { toast } from "@/components/toast";
import i18n from "@/i18n";
import { MODEL_DISCOVERY_QUERY_OPTIONS } from "@/lib/model-discovery";
import type { ModelProvider } from "@/lib/model.types";

import { syncProviderModels } from "./model-api";

export function providerSyncOptions(queryClient: QueryClient, providerId: string) {
  return {
    ...MODEL_DISCOVERY_QUERY_OPTIONS,
    queryKey: ["provider-models", providerId, "llm"] as const,
    queryFn: () => reconcileProviderModels(queryClient, providerId),
    retry: false,
  };
}

export async function reconcileProviderModels(
  queryClient: QueryClient,
  providerId: string,
  refresh = false,
) {
  try {
    const result = await syncProviderModels(providerId, refresh);
    if (!result.success) throw new Error(result.message);
    if (result.removedModels.length > 0) {
      toast.info(
        i18n.t("models.syncRemoved", {
          count: result.removedModels.length,
          names: result.removedModels.map((model) => model.name).join("、"),
        }),
        {
          description:
            result.affectedUses.length > 0
              ? `${i18n.t("models.referencesCleared")}：${result.affectedUses.join("、")}`
              : undefined,
        },
      );
    }
    return result;
  } finally {
    await invalidateModelUses(queryClient);
  }
}

export async function invalidateModelUses(queryClient: QueryClient) {
  await Promise.all(
    ["models", "settings", "agents", "agent-definitions"].map((key) =>
      queryClient.invalidateQueries({ queryKey: [key] }),
    ),
  );
}

/** One shared synchronization query per saved LLM connection, across all pages. */
export function useModelSync(providers: ModelProvider[] | undefined) {
  const queryClient = useQueryClient();
  return useQueries({
    queries: (providers ?? [])
      .filter((provider) => !provider.isBuiltin && provider.supportedTaskTypes.includes("llm"))
      .map((provider) => providerSyncOptions(queryClient, provider.id)),
  });
}
