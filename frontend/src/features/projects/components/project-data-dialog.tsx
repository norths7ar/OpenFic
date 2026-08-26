import {
  AlertDialog,
  Badge,
  Box,
  Button,
  Card,
  Dialog,
  Flex,
  ScrollArea,
  Text,
} from "@radix-ui/themes";
import { useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Archive, Check, Database, FileArchive, FileText, Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import {
  applyProjectBundleImport,
  downloadProjectBundle,
  previewProjectBundleImport,
} from "@/lib/api-client";
import type { ProjectBundlePreviewResponse } from "@/lib/api-client";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";

interface ProjectDataDialogProps {
  open: boolean;
  projectId: string;
  onOpenChange: (open: boolean) => void;
}

type ImportKind = "native" | "source";

const SUMMARY_LABELS: Record<string, string> = {
  create: "create",
  update: "update",
  delete: "delete",
  unchanged: "unchanged",
  conflict: "conflicts",
  conflicts: "conflicts",
  error: "errors",
  errors: "errors",
};

function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = detail.message;
      if (typeof message === "string") return message;
    }
  }
  return error instanceof Error ? error.message : fallback;
}

function hasBlockingSummary(preview: ProjectBundlePreviewResponse): boolean {
  const summaryBlocks = Object.entries(preview.summary).some(
    ([key, value]) => /conflict|error/i.test(key) && Number(value) > 0,
  );
  const itemBlocks = preview.items.some((item) => /conflict|error/i.test(item.action));
  return summaryBlocks || itemBlocks;
}

export function ProjectDataDialog({ open, projectId, onOpenChange }: ProjectDataDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importKind, setImportKind] = useState<ImportKind | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ProjectBundlePreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const reset = useCallback(() => {
    setImportKind(null);
    setFile(null);
    setPreview(null);
    setIsLoading(false);
    setError(null);
    setConfirmOpen(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) reset();
      onOpenChange(nextOpen);
    },
    [onOpenChange, reset],
  );

  const handleExport = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await downloadProjectBundle(projectId);
      toast.success(t("projectData.exportSuccess"));
    } catch (exportError) {
      setError(errorMessage(exportError, t("projectData.exportFailed")));
    } finally {
      setIsLoading(false);
    }
  }, [projectId, t]);

  const handlePreview = useCallback(async () => {
    if (!file || !importKind) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await previewProjectBundleImport(projectId, file, importKind === "source");
      setPreview(result);
    } catch (previewError) {
      setPreview(null);
      setError(errorMessage(previewError, t("projectData.previewFailed")));
    } finally {
      setIsLoading(false);
    }
  }, [file, importKind, projectId, t]);

  const invalidateProjectData = useCallback(async () => {
    const keys = [
      ["projects"],
      ["project", projectId],
      ["volume-tree", projectId],
      ["chapter"],
      ["chapters-search", projectId],
      projectDataQueryKeys.notes.tree(projectId),
      projectDataQueryKeys.notes.details,
      ["notes-search", projectId],
      projectDataQueryKeys.characters.list(projectId),
      projectDataQueryKeys.characters.details,
      ["characters-search", projectId],
      projectDataQueryKeys.worldInfo.byProject(projectId),
      projectDataQueryKeys.worldInfo.entriesLists,
      projectDataQueryKeys.worldInfo.entryDetails,
      ["tasks", projectId],
      ["task"],
      ["chapter-summary-list", projectId],
      ["long-term-summaries-page", projectId],
    ] as const;
    await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
  }, [projectId, queryClient]);

  const handleApply = useCallback(async () => {
    if (!file || !importKind || !preview || hasBlockingSummary(preview)) return;
    setConfirmOpen(false);
    setIsLoading(true);
    setError(null);
    try {
      await applyProjectBundleImport(projectId, file, importKind === "source");
      await invalidateProjectData();
      toast.success(t("projectData.importSuccess"));
      handleOpenChange(false);
    } catch (applyError) {
      setError(errorMessage(applyError, t("projectData.applyFailed")));
    } finally {
      setIsLoading(false);
    }
  }, [file, handleOpenChange, importKind, invalidateProjectData, preview, projectId, t]);

  const selectImportKind = (kind: ImportKind) => {
    setImportKind(kind);
    setFile(null);
    setPreview(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const summaryEntries = preview
    ? Object.entries(preview.summary).filter(([, value]) => Number.isFinite(Number(value)))
    : [];
  const blocked = preview ? hasBlockingSummary(preview) : false;

  return (
    <>
      <Dialog.Root
        open={open}
        onOpenChange={handleOpenChange}
      >
        <Dialog.Content maxWidth="620px">
          <Dialog.Title>{t("projectData.title")}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
            mb="4"
          >
            {t("projectData.description")}
          </Dialog.Description>

          {!importKind ? (
            <Flex
              direction="column"
              gap="3"
            >
              <Button
                size="3"
                variant="soft"
                onClick={() => void handleExport()}
                disabled={isLoading}
              >
                <Archive size={17} />
                {t("projectData.exportBackup")}
              </Button>
              <Button
                size="3"
                variant="soft"
                onClick={() => selectImportKind("native")}
              >
                <Database size={17} />
                {t("projectData.importBackup")}
              </Button>
              <Button
                size="3"
                variant="soft"
                onClick={() => selectImportKind("source")}
              >
                <FileText size={17} />
                {t("projectData.importSource")}
              </Button>
              <Flex justify="end">
                <Button
                  variant="soft"
                  color="gray"
                  onClick={() => handleOpenChange(false)}
                >
                  {t("common.close")}
                </Button>
              </Flex>
            </Flex>
          ) : (
            <Flex
              direction="column"
              gap="4"
            >
              <Flex
                align="center"
                justify="between"
                gap="3"
              >
                <Flex
                  align="center"
                  gap="2"
                >
                  {importKind === "native" ? <Database size={17} /> : <FileText size={17} />}
                  <Text weight="bold">
                    {importKind === "native"
                      ? t("projectData.importBackup")
                      : t("projectData.importSource")}
                  </Text>
                </Flex>
                <Button
                  variant="ghost"
                  size="1"
                  onClick={reset}
                >
                  {t("projectData.changeAction")}
                </Button>
              </Flex>

              <Box>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,application/zip"
                  hidden
                  onChange={(event) => {
                    const selectedFile = event.target.files?.[0];
                    if (selectedFile) {
                      setFile(selectedFile);
                      setPreview(null);
                      setError(null);
                    }
                  }}
                />
                <Card
                  variant="surface"
                  style={{ cursor: "pointer" }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Flex
                    align="center"
                    gap="3"
                  >
                    <Upload size={20} />
                    <Box>
                      <Text
                        as="p"
                        weight="medium"
                      >
                        {file?.name ?? t("projectData.chooseZip")}
                      </Text>
                      <Text
                        as="p"
                        size="1"
                        color="gray"
                      >
                        {t("projectData.zipHint")}
                      </Text>
                    </Box>
                  </Flex>
                </Card>
              </Box>

              <Flex
                justify="end"
                gap="2"
              >
                <Button
                  variant="soft"
                  color="gray"
                  onClick={() => handleOpenChange(false)}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => void handlePreview()}
                  disabled={!file || isLoading}
                  loading={isLoading}
                >
                  <FileArchive size={16} />
                  {t("projectData.preview")}
                </Button>
              </Flex>

              {preview && (
                <Box>
                  <Text
                    as="p"
                    weight="bold"
                    mb="2"
                  >
                    {t("projectData.previewTitle")}
                  </Text>
                  <Flex
                    wrap="wrap"
                    gap="2"
                  >
                    {summaryEntries.map(([key, value]) => (
                      <Badge
                        key={key}
                        color={/conflict|error/i.test(key) && value > 0 ? "red" : "gray"}
                      >
                        {t(`projectData.summary.${SUMMARY_LABELS[key] ?? key}`, {
                          defaultValue: key,
                        })}
                        : {value}
                      </Badge>
                    ))}
                  </Flex>
                  <Text
                    as="p"
                    size="2"
                    weight="medium"
                    mt="3"
                    mb="2"
                  >
                    {t("projectData.previewItems")}
                  </Text>
                  <ScrollArea style={{ maxHeight: 220 }}>
                    <Flex
                      direction="column"
                      gap="2"
                      pr="2"
                    >
                      {preview.items.map((item) => (
                        <Card
                          key={`${item.kind}:${item.id}`}
                          size="1"
                          variant="surface"
                        >
                          <Flex
                            align="start"
                            justify="between"
                            gap="3"
                          >
                            <Box style={{ minWidth: 0 }}>
                              <Text
                                as="p"
                                size="2"
                                weight="medium"
                                truncate
                              >
                                {item.title}
                              </Text>
                              <Text
                                as="p"
                                size="1"
                                color="gray"
                                truncate
                              >
                                {item.kind} · {item.path || item.id}
                              </Text>
                              {item.reason && (
                                <Text
                                  as="p"
                                  size="1"
                                  color="gray"
                                  mt="1"
                                >
                                  {item.reason}
                                </Text>
                              )}
                            </Box>
                            <Badge color={/conflict|error/i.test(item.action) ? "red" : "gray"}>
                              {t(
                                `projectData.summary.${SUMMARY_LABELS[item.action] ?? item.action}`,
                                { defaultValue: item.action },
                              )}
                            </Badge>
                          </Flex>
                        </Card>
                      ))}
                    </Flex>
                  </ScrollArea>
                  {blocked && (
                    <Text
                      as="p"
                      size="2"
                      color="red"
                      mt="3"
                    >
                      {t("projectData.blocked")}
                    </Text>
                  )}
                  {!blocked && (
                    <Flex
                      align="center"
                      gap="2"
                      mt="3"
                    >
                      <Check
                        size={15}
                        color="var(--green-9)"
                      />
                      <Text
                        size="2"
                        color="green"
                      >
                        {t("projectData.ready")}
                      </Text>
                    </Flex>
                  )}
                  <Flex
                    justify="end"
                    gap="2"
                    mt="4"
                  >
                    <Button
                      onClick={() => setConfirmOpen(true)}
                      disabled={blocked || isLoading}
                      loading={isLoading}
                    >
                      {t("projectData.apply")}
                    </Button>
                  </Flex>
                </Box>
              )}
            </Flex>
          )}

          {error && (
            <Text
              as="p"
              size="2"
              color="red"
              mt="3"
            >
              {error}
            </Text>
          )}
        </Dialog.Content>
      </Dialog.Root>

      <AlertDialog.Root
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
      >
        <AlertDialog.Content maxWidth="420px">
          <AlertDialog.Title>{t("projectData.confirmTitle")}</AlertDialog.Title>
          <AlertDialog.Description
            size="2"
            color="gray"
          >
            {t("projectData.confirmDescription")}
          </AlertDialog.Description>
          <Flex
            justify="end"
            gap="3"
            mt="4"
          >
            <AlertDialog.Cancel>
              <Button
                variant="soft"
                color="gray"
              >
                {t("common.cancel")}
              </Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action>
              <Button onClick={() => void handleApply()}>{t("projectData.confirmApply")}</Button>
            </AlertDialog.Action>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>
    </>
  );
}
