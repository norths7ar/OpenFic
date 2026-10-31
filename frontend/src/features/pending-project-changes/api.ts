import * as http from "@/api/generated/openfic";

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
  const response = await http.listPendingChangesApiV1ProjectsProjectIdPendingChangesGet(projectId, {
    status,
  });
  return response.data;
}

export async function countPendingProjectChanges(
  projectId: string,
  status: PendingProjectChangeStatus = "pending",
): Promise<PendingProjectChangeCountResponse> {
  const response = await http.getPendingChangeCountApiV1ProjectsProjectIdPendingChangesCountGet(
    projectId,
    { status },
  );
  return response.data;
}

export async function rejectPendingProjectChange(
  projectId: string,
  changeId: string,
  expectedUpdatedAt?: string,
): Promise<PendingProjectChange> {
  const response =
    await http.rejectPendingChangeApiV1ProjectsProjectIdPendingChangesChangeIdRejectPost(
      projectId,
      changeId,
      expectedUpdatedAt ? { expected_updated_at: expectedUpdatedAt } : undefined,
    );
  return response.data;
}

export async function applyPendingProjectChange(
  projectId: string,
  changeId: string,
  request: PendingProjectChangeApplyRequest,
): Promise<PendingProjectChange> {
  const response =
    await http.applyPendingChangeApiV1ProjectsProjectIdPendingChangesChangeIdApplyPost(
      projectId,
      changeId,
      request,
    );
  return response.data;
}

export async function getPendingProjectChange(
  projectId: string,
  changeId: string,
): Promise<PendingProjectChange> {
  const response = await http.getPendingChangeApiV1ProjectsProjectIdPendingChangesChangeIdGet(
    projectId,
    changeId,
  );
  return response.data;
}

export async function listPendingProjectChangeRevisions(
  projectId: string,
  changeId: string,
): Promise<PendingProjectChangeRevision[]> {
  const response =
    await http.listPendingChangeRevisionsApiV1ProjectsProjectIdPendingChangesChangeIdRevisionsGet(
      projectId,
      changeId,
    );
  return response.data;
}

export async function getPendingProjectChangeRevision(
  projectId: string,
  changeId: string,
  revisionId: string,
): Promise<PendingProjectChangeRevision> {
  const response =
    await http.getPendingChangeRevisionApiV1ProjectsProjectIdPendingChangesChangeIdRevisionsRevisionIdGet(
      projectId,
      changeId,
      revisionId,
    );
  return response.data;
}

export async function revisePendingProjectChange(
  projectId: string,
  changeId: string,
  expectedUpdatedAt: string,
  patch: Record<string, string>,
): Promise<PendingProjectChange> {
  const response = await http.revisePendingChangeApiV1ProjectsProjectIdPendingChangesChangeIdPatch(
    projectId,
    changeId,
    { expected_updated_at: expectedUpdatedAt, patch },
  );
  return response.data;
}
