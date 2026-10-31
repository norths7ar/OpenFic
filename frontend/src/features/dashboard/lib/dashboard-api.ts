import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";

import type {
  DashboardAuditRecord,
  DashboardBreakdownItem,
  DashboardFilterOptions,
  DashboardModelTimeSeriesPoint,
  DashboardQueryParams,
  DashboardRecordList,
  DashboardRecordPrompt,
  DashboardRecordsResponse,
  DashboardStatsResponse,
  DashboardSummary,
  DashboardTimeSeriesPoint,
  WritingActivitySummary,
  WritingActivityTimeSeriesPoint,
  WritingDashboardQueryParams,
  WritingDashboardResponse,
} from "./dashboard.types";

type RawDashboardSummary = schemas.DashboardSummary;

type RawDashboardTimeSeriesPoint = Pick<
  schemas.DashboardModelTimeSeriesPoint,
  "date" | "calls" | "tokens_total" | "avg_latency_ms"
>;

type RawDashboardModelTimeSeriesPoint = schemas.DashboardModelTimeSeriesPoint;

type RawDashboardBreakdownItem = schemas.DashboardBreakdownItem;

type RawDashboardAuditRecord = schemas.DashboardAuditRecord;

type RawDashboardRecordPrompt = schemas.DashboardRecordPrompt;

type RawDashboardRecordList = schemas.DashboardRecordList;

type RawDashboardFilterOptions = schemas.DashboardFilterOptions;

type RawWritingActivitySummary = schemas.WritingActivitySummary;

type RawWritingActivityTimeSeriesPoint = schemas.WritingActivityTimeSeriesPoint;

function transformSummary(raw: RawDashboardSummary): DashboardSummary {
  return {
    callsTotal: raw.calls_total,
    successTotal: raw.success_total,
    tokensTotal: raw.tokens_total,
    tokensInputTotal: raw.tokens_input_total,
    tokensOutputTotal: raw.tokens_output_total,
    avgLatencyMs: raw.avg_latency_ms,
    avgFirstTokenMs: raw.avg_first_token_ms,
  };
}

function transformTimeSeriesPoint(raw: RawDashboardTimeSeriesPoint): DashboardTimeSeriesPoint {
  return {
    date: raw.date,
    calls: raw.calls,
    tokensTotal: raw.tokens_total,
    avgLatencyMs: raw.avg_latency_ms,
  };
}

function transformModelTimeSeriesPoint(
  raw: RawDashboardModelTimeSeriesPoint,
): DashboardModelTimeSeriesPoint {
  return {
    ...transformTimeSeriesPoint(raw),
    key: raw.key,
    label: raw.label,
  };
}

function transformBreakdownItem(raw: RawDashboardBreakdownItem): DashboardBreakdownItem {
  return {
    key: raw.key,
    label: raw.label,
    calls: raw.calls,
    tokensTotal: raw.tokens_total,
  };
}

function transformRecord(raw: RawDashboardAuditRecord): DashboardAuditRecord {
  return {
    id: raw.id,
    createdAt: raw.created_at,
    taskId: raw.task_id,
    sessionId: raw.session_id,
    projectId: raw.project_id,
    projectTitle: raw.project_title,
    chapterId: raw.chapter_id,
    revisionId: raw.revision_id,
    category: raw.category,
    operation: raw.operation,
    modelId: raw.model_id,
    modelProvider: raw.model_provider,
    modelName: raw.model_name,
    tokensInput: raw.tokens_input,
    tokensOutput: raw.tokens_output,
    tokensTotal: raw.tokens_total,
    tokenCache: raw.token_cache,
    latencyMs: raw.latency_ms,
    firstTokenMs: raw.first_token_ms,
    status: raw.status,
    errorType: raw.error_type,
    errorMessage: raw.error_message,
    errorStatusCode: raw.error_status_code,
    toolCallsCount: raw.tool_calls_count,
    hasRequestMessages: raw.has_request_messages,
    toolReferences: raw.tool_references,
    responseContent: raw.response_content,
    responseToolCalls: raw.response_tool_calls,
  };
}

function transformRecordPrompt(raw: RawDashboardRecordPrompt): DashboardRecordPrompt {
  return {
    id: raw.id,
    requestMessages: raw.request_messages,
  };
}

function transformRecords(raw: RawDashboardRecordList): DashboardRecordList {
  return {
    items: raw.items.map(transformRecord),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
  };
}

function transformOptions(raw: RawDashboardFilterOptions): DashboardFilterOptions {
  return {
    projectIds: raw.project_ids,
    modelProviders: raw.model_providers,
    modelIds: raw.model_ids,
    categories: raw.categories,
    operations: raw.operations,
    statuses: raw.statuses,
    projectOptions: raw.project_options.map((option) => ({
      value: option.value,
      label: option.label,
    })),
    modelOptions: raw.model_options.map((option) => ({ value: option.value, label: option.label })),
  };
}

function transformWritingSummary(raw: RawWritingActivitySummary): WritingActivitySummary {
  return {
    activeDays: raw.active_days,
    creativeChapters: raw.creative_chapters,
  };
}

function transformWritingTimeSeriesPoint(
  raw: RawWritingActivityTimeSeriesPoint,
): WritingActivityTimeSeriesPoint {
  return {
    date: raw.date,
    userWordDelta: raw.user_word_delta,
    agentWordDelta: raw.agent_word_delta,
    importWordDelta: raw.import_word_delta,
  };
}

export async function fetchLlmDashboardStats(
  query: DashboardQueryParams,
): Promise<DashboardStatsResponse> {
  const response = await http.getLlmApiStatsDashboardApiV1DashboardLlmApiStatsGet({
    project_id: query.projectId || undefined,
    model_provider: query.modelProvider || undefined,
    model_id: query.modelId || undefined,
    category: query.category || undefined,
    operation: query.operation || undefined,
    status: query.status || undefined,
    start_at: query.startAt || undefined,
    end_at: query.endAt || undefined,
  });
  const raw = response.data;
  return {
    summary: transformSummary(raw.summary),
    modelTimeSeries: raw.model_time_series.map(transformModelTimeSeriesPoint),
    byModel: raw.by_model.map(transformBreakdownItem),
    byProject: raw.by_project.map(transformBreakdownItem),
    options: transformOptions(raw.options),
  };
}

export async function fetchLlmDashboardRecords(
  query: DashboardQueryParams,
): Promise<DashboardRecordsResponse> {
  const response = await http.getLlmApiRecordsDashboardApiV1DashboardLlmApiRecordsGet({
    project_id: query.projectId || undefined,
    model_provider: query.modelProvider || undefined,
    model_id: query.modelId || undefined,
    category: query.category || undefined,
    operation: query.operation || undefined,
    status: query.status || undefined,
    task_id: query.taskId || undefined,
    session_id: query.sessionId || undefined,
    start_at: query.startAt || undefined,
    end_at: query.endAt || undefined,
    search: query.search || undefined,
    page: query.page,
    page_size: query.pageSize,
    sort_by: query.sortBy,
    sort_order: query.sortOrder,
  });
  const raw = response.data;
  return {
    options: transformOptions(raw.options),
    records: transformRecords(raw.records),
  };
}

export async function fetchDashboardRecordPrompt(recordId: string): Promise<DashboardRecordPrompt> {
  const response =
    await http.getLlmApiRecordPromptApiV1DashboardLlmApiRecordsRecordIdPromptGet(recordId);
  return transformRecordPrompt(response.data);
}

export async function fetchWritingDashboard(
  query: WritingDashboardQueryParams,
): Promise<WritingDashboardResponse> {
  const response = await http.getWritingDashboardApiV1DashboardWritingGet({
    project_id: query.projectId || undefined,
    source: query.source || undefined,
    start_at: query.startAt || undefined,
    end_at: query.endAt || undefined,
    timezone: query.timezone || undefined,
  });
  const raw = response.data;
  return {
    summary: transformWritingSummary(raw.summary),
    timeSeries: raw.time_series.map(transformWritingTimeSeriesPoint),
  };
}
