import * as http from "@/api/generated/openfic";

export type AuthStatusResponse = import("@/api/generated/models").AuthStatusResponse;

export type AuthPreferencesResponse = import("@/api/generated/models").PublicPreferencesResponse;

export type AuthLoginRequest = import("@/api/generated/models").AuthLoginRequest;

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
  const response = await http.authStatusApiV1AuthStatusGet();
  return response.data;
}

export async function fetchAuthPreferences(): Promise<AuthPreferencesResponse> {
  const response = await http.publicPreferencesApiV1AuthPreferencesGet();
  return response.data;
}

export async function loginWithPassword(payload: AuthLoginRequest): Promise<AuthStatusResponse> {
  const response = await http.loginApiV1AuthLoginPost(payload);
  return response.data;
}
