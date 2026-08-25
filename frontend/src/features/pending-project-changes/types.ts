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
  source_task_id: string | null;
  source_message_id: string | null;
  model_id: string | null;
  status: PendingProjectChangeStatus;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PendingProjectChangeCountResponse {
  count: number;
}
