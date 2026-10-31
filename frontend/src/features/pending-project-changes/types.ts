export type PendingProjectChangeStatus = "pending" | "applying" | "rejected" | "applied";

export type PendingProjectChangeOperation = "create" | "update" | "delete";

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type PendingProjectChange = import("@/api/generated/models").PendingProjectChangeResponse;

export type PendingProjectChangeRevision =
  import("@/api/generated/models").PendingProjectChangeRevisionResponse;

export type PendingProjectChangeApplyRequest =
  import("@/api/generated/models").PendingProjectChangeApply;

export type PendingProjectChangeCountResponse = import("@/api/generated/models").CountResponse;
