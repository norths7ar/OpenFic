import * as http from "@/api/generated/openfic";

export type HealthResponse = import("@/api/generated/models").HealthResponse;

export async function checkHealth(): Promise<HealthResponse> {
  const response = await http.healthCheckApiV1HealthGet();
  return response.data;
}
