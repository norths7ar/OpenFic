import { useQuery } from "@tanstack/react-query";

import { agentVisibilityCatalogSchema } from "@/lib/agent-visibility";
import { apiClient } from "@/lib/api-transport";

export function useAgentVisibilityCatalog() {
  return useQuery({
    queryKey: ["agent-visibility"],
    queryFn: async () => {
      const response = await apiClient.get<unknown>("/agent-visibility");
      return agentVisibilityCatalogSchema.parse(response.data);
    },
    staleTime: Infinity,
  });
}
