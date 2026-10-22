export type PendingProjectChangeStatus = "pending" | "applying" | "rejected" | "applied";

export type PendingProjectChangeOperation = "create" | "update" | "delete";

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface PendingProjectChange {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string | null;
  operation: PendingProjectChangeOperation;
  base_hash: string | null;
  before: JsonValue;
  after: JsonValue;
  current: JsonValue;
  current_hash: string | null;
  current_revision_id: string | null;
  applied_revision_id: string | null;
  source_task_id: string | null;
  source_message_id: string | null;
  model_id: string | null;
  status: PendingProjectChangeStatus;
  is_applicable: boolean;
  applicability_reason: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PendingProjectChangeRevision {
  id: string;
  change_id: string;
  after: JsonValue;
  source: "manual" | "ai" | "migration";
  source_task_id: string | null;
  source_message_id: string | null;
  model_id: string | null;
  created_at: string;
}

export interface PendingProjectChangeApplyRequest {
  expected_updated_at: string;
  expected_current_hash: string | null;
  revision_id: string;
}

export interface PendingProjectChangeCountResponse {
  count: number;
}
