import { apiClient } from "@/lib/api-transport";

import type {
  PendingProjectChange,
  PendingProjectChangeCountResponse,
  PendingProjectChangeStatus,
} from "./types";

export async function listPendingProjectChanges(
  projectId: string,
  status?: PendingProjectChangeStatus,
): Promise<PendingProjectChange[]> {
  const response = await apiClient.get<PendingProjectChange[]>(
    `/projects/${projectId}/pending-changes`,
    { params: { status } },
  );
  return response.data;
}

export async function countPendingProjectChanges(
  projectId: string,
  status: PendingProjectChangeStatus = "pending",
): Promise<PendingProjectChangeCountResponse> {
  const response = await apiClient.get<PendingProjectChangeCountResponse>(
    `/projects/${projectId}/pending-changes/count`,
    { params: { status } },
  );
  return response.data;
}

export async function rejectPendingProjectChange(
  projectId: string,
  changeId: string,
): Promise<PendingProjectChange> {
  const response = await apiClient.post<PendingProjectChange>(
    `/projects/${projectId}/pending-changes/${changeId}/reject`,
  );
  return response.data;
}

export async function applyPendingProjectChange(
  projectId: string,
  changeId: string,
): Promise<PendingProjectChange> {
  const response = await apiClient.post<PendingProjectChange>(
    `/projects/${projectId}/pending-changes/${changeId}/apply`,
  );
  return response.data;
}
