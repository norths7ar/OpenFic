// Refresh while the application is visible, and recheck when returning to it.
// The backend shares a five-minute discovery cache across clients.
export const MODEL_DISCOVERY_QUERY_OPTIONS = {
  staleTime: 0,
  refetchInterval: 5 * 60 * 1000,
  refetchIntervalInBackground: false,
  refetchOnMount: "always",
  refetchOnWindowFocus: "always",
  refetchOnReconnect: "always",
} as const;
