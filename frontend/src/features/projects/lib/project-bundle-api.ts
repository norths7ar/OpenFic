import * as http from "@/api/generated/openfic";

export type ProjectBundlePreviewItem = import("@/api/generated/models").PreviewItem;
export type ProjectBundlePreviewResponse = import("@/api/generated/models").BundleApplyResponse &
  Partial<Pick<import("@/api/generated/models").BundlePreviewResponse, "source_project">> &
  Partial<Pick<import("@/api/generated/models").SourceBundleResponse, "source_items">>;

async function postProjectBundleImport(
  projectId: string,
  file: File,
  endpoint: "bundle/import" | "bundle/source",
  action: "preview" | "apply",
): Promise<ProjectBundlePreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("mode", "merge");
  const operation =
    endpoint === "bundle/source"
      ? action === "preview"
        ? http.previewSourceBundleImportApiV1ProjectsProjectIdBundleSourcePreviewPost
        : http.applySourceBundleImportApiV1ProjectsProjectIdBundleSourceApplyPost
      : action === "preview"
        ? http.previewBundleImportApiV1ProjectsProjectIdBundleImportPreviewPost
        : http.applyBundleImportApiV1ProjectsProjectIdBundleImportApplyPost;
  const response = await operation(projectId, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
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
  const operation = source
    ? http.exportSourceBundleApiV1ProjectsProjectIdBundleSourceExportGet
    : http.exportBundleApiV1ProjectsProjectIdBundleExportGet;
  const response = await operation(projectId, {
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
