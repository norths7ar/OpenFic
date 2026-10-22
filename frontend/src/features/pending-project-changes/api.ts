import { apiClient } from "@/lib/api-transport";

import type {
  PendingProjectChange,
  PendingProjectChangeApplyRequest,
  PendingProjectChangeCountResponse,
  PendingProjectChangeRevision,
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
  expectedUpdatedAt?: string,
): Promise<PendingProjectChange> {
  const response = await apiClient.post<PendingProjectChange>(
    `/projects/${projectId}/pending-changes/${changeId}/reject`,
    expectedUpdatedAt ? { expected_updated_at: expectedUpdatedAt } : undefined,
  );
  return response.data;
}

export async function applyPendingProjectChange(
  projectId: string,
  changeId: string,
  request: PendingProjectChangeApplyRequest,
): Promise<PendingProjectChange> {
  const response = await apiClient.post<PendingProjectChange>(
    `/projects/${projectId}/pending-changes/${changeId}/apply`,
    request,
  );
  return response.data;
}

export async function getPendingProjectChange(
  projectId: string,
  changeId: string,
): Promise<PendingProjectChange> {
  const response = await apiClient.get<PendingProjectChange>(
    `/projects/${projectId}/pending-changes/${changeId}`,
  );
  return response.data;
}

export async function listPendingProjectChangeRevisions(
  projectId: string,
  changeId: string,
): Promise<PendingProjectChangeRevision[]> {
  const response = await apiClient.get<PendingProjectChangeRevision[]>(
    `/projects/${projectId}/pending-changes/${changeId}/revisions`,
  );
  return response.data;
}

export async function getPendingProjectChangeRevision(
  projectId: string,
  changeId: string,
  revisionId: string,
): Promise<PendingProjectChangeRevision> {
  const response = await apiClient.get<PendingProjectChangeRevision>(
    `/projects/${projectId}/pending-changes/${changeId}/revisions/${revisionId}`,
  );
  return response.data;
}

export async function revisePendingProjectChange(
  projectId: string,
  changeId: string,
  expectedUpdatedAt: string,
  patch: Record<string, string>,
): Promise<PendingProjectChange> {
  const response = await apiClient.patch<PendingProjectChange>(
    `/projects/${projectId}/pending-changes/${changeId}`,
    { expected_updated_at: expectedUpdatedAt, patch },
  );
  return response.data;
}
