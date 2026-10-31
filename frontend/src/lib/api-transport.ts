/**
 * Shared HTTP transport for the backend API.
 *
 * Feature APIs depend on this module; it must not depend on feature modules.
 */

import axios, { type AxiosRequestConfig, type AxiosResponse } from "axios";

import { handleAuthenticationFailure } from "./auth-failure";
import { getConfiguredBackendBaseUrl, getRuntimeConfig } from "./runtime-config";

function getBackendBaseUrl(): string | null {
  return getRuntimeConfig()?.backendBaseUrl ?? getConfiguredBackendBaseUrl();
}

export function getApiBaseUrl(): string {
  const backendBaseUrl = getBackendBaseUrl();
  if (backendBaseUrl) return `${backendBaseUrl}/api/v1`;
  return "/api/v1";
}

/**
 * Resolves a backend-provided root-relative URL for the desktop webview.
 * Browser deployments keep root-relative URLs so the frontend origin serves them.
 */
export function resolveBackendUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (!url.startsWith("/") || url.startsWith("//")) return url;

  const backendBaseUrl = getBackendBaseUrl();
  return backendBaseUrl ? `${backendBaseUrl}${url}` : url;
}

export function getApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl().replace(/\/+$/, "")}${normalizedPath}`;
}

export const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 120000,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

/** Generated endpoints retain the full HTTP response for downloads and headers. */
export function request<T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<T>> {
  return apiClient({
    ...config,
    ...options,
    url: config.url?.replace(/^\/api\/v1(?=\/|$)/, ""),
  });
}

/** Multipart callers may supply files using the browser's native FormData. */
export type BodyType<T> = T | FormData;

function isAuthenticationRequest(url: string | undefined): boolean {
  return url?.includes("/auth/") ?? false;
}

apiClient.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !isAuthenticationRequest(error.config?.url)) {
      handleAuthenticationFailure();
    }
    if (import.meta.env.DEV) {
      console.error("API Error:", error);
    }
    return Promise.reject(error);
  },
);
