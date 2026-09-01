import { getApiBaseUrl, resolveBackendUrl } from "@/lib/api-transport";

export function getProviderIconUrl(iconPath?: string | null): string | null {
  if (!iconPath) {
    return null;
  }

  if (iconPath.startsWith("/")) {
    return resolveBackendUrl(iconPath);
  }

  return `${getApiBaseUrl()}/${iconPath.replace(/^\/+/, "")}`;
}
