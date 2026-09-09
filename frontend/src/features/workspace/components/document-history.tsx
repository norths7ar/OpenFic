import {
  AlertDialog,
  Box,
  Button,
  Dialog,
  Flex,
  IconButton,
  Text,
  Tooltip,
} from "@radix-ui/themes";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { History, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StreamingMarkdown } from "@/components/streaming-markdown";
import { toast } from "@/components/toast";
import { apiClient } from "@/lib/api-transport";

import "./document-history.css";

export type DocumentKind = "chapter" | "world_entry" | "character" | "note" | "outline";
export interface DocumentHistoryConfig {
  projectId: string;
  kind: DocumentKind;
  documentId: string;
  prepare: () => Promise<boolean>;
  disabled?: boolean;
}
interface Snapshot {
  id: string;
  document_id: string;
  kind: DocumentKind;
  title: string;
  content?: string;
  created_at?: string;
  deleted_at?: string;
  source?: string;
}

export function DocumentHistoryButton({ config }: { config: DocumentHistoryConfig }) {
  return (
    <DocumentArchive
      projectId={config.projectId}
      history={config}
    />
  );
}

export function DocumentTrashButton({ projectId }: { projectId: string }) {
  return <DocumentArchive projectId={projectId} />;
}

/** One browser for saved versions and deleted documents across all editing workspaces. */
function DocumentArchive({
  projectId,
  history,
}: {
  projectId: string;
  history?: DocumentHistoryConfig;
}) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [baseUpdatedAt, setBaseUpdatedAt] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const label = t(history ? "documentArchive.history" : "documentArchive.trash");
  const path = history
    ? `/projects/${projectId}/documents/${history.kind}/${history.documentId}/history`
    : `/projects/${projectId}/trash`;
  const prepare = async () => {
    if (history && !(await history.prepare())) {
      toast.error(t("documentArchive.saveFirst"));
      return false;
    }
    return true;
  };
  const load = async () => {
    const { data } = await apiClient.get<{ items: Snapshot[]; current_updated_at?: string }>(path);
    setItems(data.items);
    setBaseUpdatedAt(data.current_updated_at ?? "");
    setSelected(null);
  };
  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await action();
    } catch (error) {
      const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
      toast.error(
        isAxiosError(error) && error.response?.status === 409 && typeof detail === "string"
          ? detail
          : t("documentArchive.failed"),
      );
    } finally {
      setBusy(false);
    }
  };
  const restore = () =>
    run(async () => {
      if (!selected || !(await prepare())) return;
      await apiClient.post(
        `${path}/${selected.id}/restore`,
        history ? { base_updated_at: baseUpdatedAt } : undefined,
      );
      const prefixes: Record<DocumentKind, string[]> = {
        chapter: [
          "writing-editor",
          "chapter",
          "volume-tree",
          "chapter-summary-list",
          "long-term-summaries-page",
          "projects",
        ],
        note: ["writing-editor", "note", "note-tree"],
        outline: ["writing-editor", "note", "note-tree"],
        character: ["character", "characters", "characters-search"],
        world_entry: ["world-info-entry-detail", "world-info-entries", "world-info-entries-search"],
      };
      await queryClient.invalidateQueries({
        predicate: (query) => prefixes[selected.kind].includes(String(query.queryKey[0])),
      });
      toast.success(t("documentArchive.restored"));
      setOpen(false);
    });
  return (
    <>
      <Tooltip content={label}>
        <IconButton
          variant="ghost"
          size="2"
          aria-label={label}
          disabled={busy || history?.disabled}
          onClick={() =>
            void run(async () => {
              if (!(await prepare())) return;
              await load();
              setOpen(true);
            })
          }
        >
          {history ? <History size={18} /> : <Trash2 size={18} />}
        </IconButton>
      </Tooltip>
      <Dialog.Root
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
      >
        <Dialog.Content
          maxWidth="1100px"
          className="document-archive-dialog"
        >
          <Dialog.Title>{label}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
          >
            {t(history ? "documentArchive.historyHint" : "documentArchive.trashHint")}
          </Dialog.Description>
          <div className="document-archive-body">
            <div
              className="document-archive-list"
              aria-label={label}
            >
              {items.length === 0 && (
                <Text
                  size="2"
                  color="gray"
                >
                  {t("documentArchive.empty")}
                </Text>
              )}
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="document-archive-item"
                  aria-pressed={selected?.id === item.id}
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      setSelected(null);
                      setSelected(
                        history ? (await apiClient.get<Snapshot>(`${path}/${item.id}`)).data : item,
                      );
                    })
                  }
                >
                  <Text
                    as="div"
                    size="2"
                    weight="medium"
                  >
                    {item.title}
                  </Text>
                  <Text
                    as="div"
                    size="1"
                    color="gray"
                  >
                    {new Date(item.created_at ?? item.deleted_at ?? "").toLocaleString(
                      i18n.language,
                    )}
                  </Text>
                  <Text
                    as="div"
                    size="1"
                    color="gray"
                  >
                    {history
                      ? t(`documentArchive.sources.${item.source}`, {
                          defaultValue: item.source ?? "",
                        })
                      : t(`documentArchive.kinds.${item.kind}`)}
                  </Text>
                </button>
              ))}
            </div>
            <Box className="document-archive-preview">
              {selected ? (
                <>
                  <Text
                    as="div"
                    size="5"
                    weight="bold"
                    mb="4"
                  >
                    {selected.title}
                  </Text>
                  {selected.kind === "chapter" ? (
                    <div
                      style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", lineHeight: 1.8 }}
                    >
                      {selected.content}
                    </div>
                  ) : (
                    <StreamingMarkdown content={selected.content ?? ""} />
                  )}
                </>
              ) : (
                <Text
                  color="gray"
                  size="2"
                >
                  {t("documentArchive.select")}
                </Text>
              )}
            </Box>
          </div>
          <Flex
            justify="end"
            gap="3"
            mt="4"
            wrap="wrap"
          >
            {!history && (
              <Button
                color="red"
                variant="soft"
                disabled={!selected || busy}
                onClick={() => setConfirmDelete(true)}
              >
                {t("documentArchive.delete")}
              </Button>
            )}
            <Dialog.Close>
              <Button
                variant="soft"
                color="gray"
                disabled={busy}
              >
                {t("documentArchive.close")}
              </Button>
            </Dialog.Close>
            <Button
              disabled={!selected || busy || history?.disabled}
              loading={busy}
              onClick={() => void restore()}
            >
              {t("documentArchive.restore")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
      <AlertDialog.Root
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
      >
        <AlertDialog.Content maxWidth="440px">
          <AlertDialog.Title>{t("documentArchive.delete")}</AlertDialog.Title>
          <AlertDialog.Description>
            {t("documentArchive.deleteHint", { title: selected?.title })}
          </AlertDialog.Description>
          <Flex
            justify="end"
            gap="3"
            mt="4"
          >
            <AlertDialog.Cancel>
              <Button
                color="gray"
                variant="soft"
              >
                {t("documentArchive.cancel")}
              </Button>
            </AlertDialog.Cancel>
            <Button
              color="red"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  if (!selected) return;
                  await apiClient.delete(`${path}/${selected.id}`);
                  setConfirmDelete(false);
                  await load();
                })
              }
            >
              {t("documentArchive.delete")}
            </Button>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>
    </>
  );
}
