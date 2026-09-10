import i18n from "@/i18n";
import type { AgentMessage } from "@/lib/agent.types";

import {
  asString,
  getStreamingData,
  getToolResultData,
  isRecord,
} from "../shared/tool-message-utils";

export function getProjectChangeSummary(message: AgentMessage) {
  const result = getToolResultData(message);
  const record = isRecord(result) ? result : null;
  const change = isRecord(record?.pending_change) ? record.pending_change : record;
  const before = isRecord(change?.before) ? change.before : null;
  const after = isRecord(change?.after) ? change.after : null;
  const args = getStreamingData(message);
  const type = asString(change?.target_type) ?? asString(args.target_type);
  const documentType =
    asString(change?.document_type) ??
    asString(after?.document_type) ??
    asString(before?.document_type) ??
    asString(args.document_type);
  const material =
    type === "world_entry"
      ? "worldEntry"
      : type === "character"
        ? "character"
        : type === "note"
          ? documentType === "outline"
            ? "outline"
            : "note"
          : type === "note_category"
            ? documentType === "outline"
              ? "outlineCategory"
              : "noteCategory"
            : "material";
  const operation =
    asString(change?.operation) ??
    (message.toolName === "propose_project_create"
      ? "create"
      : message.toolName === "propose_project_delete"
        ? "delete"
        : "update");
  const title =
    asString(change?.title) ??
    asString(after?.title) ??
    asString(before?.title) ??
    asString(args.title);
  const snapshotFieldsSupported = [
    "title",
    "body",
    "agent_visibility",
    "section",
    "category_id",
    "document_type",
  ];
  const snapshotFields = snapshotFieldsSupported.filter(
    (key) => before && after && JSON.stringify(before[key]) !== JSON.stringify(after[key]),
  );
  const fields = Array.isArray(change?.changed_fields)
    ? change.changed_fields.filter(
        (field): field is string =>
          typeof field === "string" && snapshotFieldsSupported.includes(field),
      )
    : snapshotFields;
  return { change, title, material, operation, fields };
}

export function getProjectChangeDetail(message: AgentMessage) {
  const { title, material } = getProjectChangeSummary(message);
  return title ?? i18n.t(`pendingProjectChanges.materialTypes.${material}`);
}
