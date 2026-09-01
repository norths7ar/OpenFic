import { apiClient } from "@/lib/api-transport";

export interface AuthStatusResponse {
  enabled: boolean;
  authenticated: boolean;
}

export interface AuthPreferencesResponse {
  language: string;
  theme: string;
  font_family: string;
  code_font_family: string;
  base_font_size: number;
  editor_font_size: number;
}

export interface AuthLoginRequest {
  password: string;
  trust_device: boolean;
}

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
  const response = await apiClient.get<AuthStatusResponse>("/auth/status");
  return response.data;
}

export async function fetchAuthPreferences(): Promise<AuthPreferencesResponse> {
  const response = await apiClient.get<AuthPreferencesResponse>("/auth/preferences");
  return response.data;
}

export async function loginWithPassword(payload: AuthLoginRequest): Promise<AuthStatusResponse> {
  const response = await apiClient.post<AuthStatusResponse>("/auth/login", payload);
  return response.data;
}
