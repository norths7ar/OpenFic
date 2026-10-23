import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MODEL_DISCOVERY_QUERY_OPTIONS } from "@/lib/model-discovery";
import type { TaskType } from "@/lib/model.types";

import { fetchProviderModels } from "./model-api";
import { reconcileProviderModels } from "./use-model-sync";

export function useProviderModelsQuery(
  providerId: string | undefined,
  taskType: TaskType,
  enabled: boolean,
) {
  const queryClient = useQueryClient();
  const queryKey = ["provider-models", providerId, taskType] as const;
  const fetchDirectory = async (refresh: boolean, signal: AbortSignal) => {
    try {
      const result =
        taskType === "llm"
          ? await reconcileProviderModels(queryClient, providerId!, refresh)
          : await fetchProviderModels(providerId!, taskType, refresh);
      signal.throwIfAborted();
      if (!result.success) throw new Error(result.message);
      return result;
    } finally {
      // Discovery also updates the status of saved models, including failed probes.
      if (taskType !== "llm" && !signal.aborted)
        void queryClient.invalidateQueries({ queryKey: ["models"] });
    }
  };

  const query = useQuery({
    ...MODEL_DISCOVERY_QUERY_OPTIONS,
    queryKey,
    queryFn: ({ signal }) => fetchDirectory(false, signal),
    enabled: enabled && Boolean(providerId),
    retry: false,
  });

  const refresh = useMutation({
    mutationFn: async () => {
      await queryClient.cancelQueries({ queryKey, exact: true });
      return queryClient.fetchQuery({
        queryKey,
        queryFn: ({ signal }) => fetchDirectory(true, signal),
        staleTime: 0,
        retry: false,
      });
    },
  });

  return { ...query, refresh: () => refresh.mutate(), isRefreshing: refresh.isPending };
}
