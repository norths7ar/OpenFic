import { apiClient } from "@/lib/api-transport";

/**
 * 上下文部分响应
 */
export interface ContextPartResponse {
  content: string;
  token_count: number;
  chapter_range: [number, number];
}

/**
 * 构建的上下文响应
 */
export interface BuiltContextResponse {
  latest_field: ContextPartResponse;
  near_field: ContextPartResponse;
  mid_field: ContextPartResponse;
  far_field: ContextPartResponse;
}

/**
 * 获取构建的章节上下文
 */
export async function fetchChapterContext(
  projectId: string,
  currentOrder: number,
): Promise<BuiltContextResponse> {
  const response = await apiClient.get<BuiltContextResponse>(
    `/projects/${projectId}/chapter-context/context`,
    {
      params: {
        current_order: currentOrder,
      },
    },
  );
  return response.data;
}
