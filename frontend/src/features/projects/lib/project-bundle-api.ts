import { apiClient } from "@/lib/api-transport";

export interface ProjectBundlePreviewItem {
  kind: string;
  id: string;
  title: string;
  path: string;
  action: string;
  reason: string;
  base_hash: string;
  current_hash: string | null;
  incoming_hash: string;
}

export interface ProjectBundlePreviewResponse {
  mode: string;
  source_project?: Record<string, unknown>;
  items: ProjectBundlePreviewItem[];
  summary: Record<string, number>;
  source_items?: Record<string, unknown>[];
}

async function postProjectBundleImport(
  projectId: string,
  file: File,
  endpoint: "bundle/import" | "bundle/source",
  action: "preview" | "apply",
): Promise<ProjectBundlePreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("mode", "merge");
  const response = await apiClient.post<ProjectBundlePreviewResponse>(
    `/projects/${projectId}/${endpoint}/${action}`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return response.data;
}

export async function previewProjectBundleImport(
  projectId: string,
  file: File,
  source = false,
): Promise<ProjectBundlePreviewResponse> {
  return postProjectBundleImport(
    projectId,
    file,
    source ? "bundle/source" : "bundle/import",
    "preview",
  );
}

export async function applyProjectBundleImport(
  projectId: string,
  file: File,
  source = false,
): Promise<ProjectBundlePreviewResponse> {
  return postProjectBundleImport(
    projectId,
    file,
    source ? "bundle/source" : "bundle/import",
    "apply",
  );
}

export async function downloadProjectBundle(projectId: string, source = false): Promise<void> {
  const endpoint = source ? "bundle/source/export" : "bundle/export";
  const response = await apiClient.get<Blob>(`/projects/${projectId}/${endpoint}`, {
    responseType: "blob",
  });
  const contentDisposition = response.headers["content-disposition"] as string | undefined;
  const encodedFilename = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plainFilename = contentDisposition?.match(/filename="?([^";]+)"?/i)?.[1];
  let filename =
    plainFilename ?? (source ? "openfic-markdown-source.zip" : "openfic-project-bundle.zip");
  if (encodedFilename) {
    try {
      filename = decodeURIComponent(encodedFilename);
    } catch {
      // Keep the RFC 5987 fallback name when the server header is malformed.
    }
  }
  const url = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
