import { useQuery } from "@tanstack/react-query";

import * as http from "@/api/generated/openfic";
import { agentVisibilityCatalogSchema } from "@/lib/agent-visibility";

export function useAgentVisibilityCatalog() {
  return useQuery({
    queryKey: ["agent-visibility"],
    queryFn: async () => {
      const response = await http.getAgentVisibilityCatalogApiV1AgentVisibilityGet();
      return agentVisibilityCatalogSchema.parse(response.data);
    },
    staleTime: Infinity,
  });
}
