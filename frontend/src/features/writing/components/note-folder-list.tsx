import {
  closestCenter,
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { IconButton } from "@radix-ui/themes";
import { GripVertical, Lock, MoreHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentVisibilityButton } from "@/components/agent-visibility-button";
import { ProjectFolderGroups } from "@/features/project-navigation/components/project-folder-groups";
import { ProjectNavItemRow } from "@/features/project-navigation/components/project-nav-item-row";
import type { NoteListItem, NoteTreeResponse } from "@/lib/note.types";
import { formatRelativeTime } from "@/lib/time-utils";

export type NoteSortMode = "manual" | "title" | "updated";
export type NoteAgentVisibility = string;
interface NoteFolderListProps {
  data: NoteTreeResponse | undefined;
  emptyLabel?: string;
  onNoteSelect: (id: string, title: string) => void;
  onCategorySelect: (id: string) => void;
  currentNoteId: string | null;
  selectedCategoryId: string | null;
  renamingId: string | null;
  onRenameConfirm: (id: string, kind: "category" | "note", title: string) => void;
  onRenameCancel: () => void;
  onContextMenu: (
    id: string,
    kind: "category" | "note",
    position: { x: number; y: number },
    title: string,
  ) => void;
  onMove: (id: string, kind: "category" | "note", target: string | null) => Promise<void>;
  onReorder: (
    parent: string | null,
    items: Array<{ id: string; kind: "category" | "note" }>,
  ) => Promise<void>;
  onSetAgentVisibility: (id: string, visibility: NoteAgentVisibility) => void;
  isAgentLocked: boolean;
  sortMode: NoteSortMode;
}
function NoteRow({ note, options }: { note: NoteListItem; options: NoteFolderListProps }) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(note.title);
  useEffect(() => {
    setTitle(note.title);
  }, [note.title, options.renamingId]);
  const { setNodeRef, attributes, listeners, transform, transition, isDragging } = useSortable({
    id: note.id,
    disabled: note.isLocked || options.isAgentLocked || options.sortMode !== "manual",
  });
  const menu = (x: number, y: number) =>
    options.onContextMenu(note.id, "note", { x, y }, note.title);
  return (
    <ProjectNavItemRow
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      selected={options.currentNoteId === note.id}
      dragging={isDragging}
      onClick={() => options.renamingId !== note.id && options.onNoteSelect(note.id, note.title)}
      onContextMenu={(e) => {
        e.preventDefault();
        menu(e.clientX, e.clientY);
      }}
      leading={
        options.sortMode === "manual" && (
          <span
            {...attributes}
            {...listeners}
            style={{ display: "flex", touchAction: "none" }}
            onClick={(e) => e.stopPropagation()}
          >
            <GripVertical size={16} />
          </span>
        )
      }
      title={
        options.renamingId === note.id ? (
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onBlur={() =>
              title.trim()
                ? options.onRenameConfirm(note.id, "note", title.trim())
                : options.onRenameCancel()
            }
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") options.onRenameCancel();
            }}
            style={{
              width: "100%",
              border: 0,
              background: "transparent",
              color: "inherit",
              font: "inherit",
            }}
          />
        ) : (
          note.title
        )
      }
      metadata={formatRelativeTime(note.updatedAt)}
      status={note.isLocked && <Lock size={12} />}
      actions={
        <>
          <AgentVisibilityButton
            value={note.agentVisibility}
            disabled={note.isLocked || options.isAgentLocked}
            onChange={(value) => options.onSetAgentVisibility(note.id, value)}
          />
          <IconButton
            className="project-nav-item-more"
            variant="ghost"
            size="1"
            aria-label={t("common.more")}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              const r = e.currentTarget.getBoundingClientRect();
              menu(r.left, r.bottom);
            }}
          >
            <MoreHorizontal size={14} />
          </IconButton>
        </>
      }
    />
  );
}
export function NoteFolderList(options: NoteFolderListProps) {
  const { t } = useTranslation();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const { data } = options;
  if (!data) return null;
  const compare = (a: { title: string; order: number; updatedAt: string }, b: typeof a) =>
    options.sortMode === "title"
      ? a.title.localeCompare(b.title)
      : options.sortMode === "updated"
        ? b.updatedAt.localeCompare(a.updatedAt)
        : a.order - b.order;
  const folders = data.categories
    .map((folder) => ({
      id: folder.id,
      projectId: folder.projectId,
      title: folder.title,
      description: folder.description,
      scope: folder.documentType,
      order: folder.order,
      createdAt: folder.createdAt,
      updatedAt: folder.updatedAt,
    }))
    .sort(compare);
  const items = [...data.rootNotes, ...data.categories.flatMap((folder) => folder.notes)]
    .map((note) => ({ ...note, folderId: note.categoryId }))
    .sort(compare);
  const onDragEnd = async ({ active, over }: DragEndEvent) => {
    if (!over || options.isAgentLocked || options.sortMode !== "manual") return;
    const item = items.find((item) => item.id === active.id);
    if (!item || item.isLocked) return;
    const target = items.find((item) => item.id === over.id);
    const folderId = target?.folderId ?? over.data.current?.folderId ?? null;
    if (item.folderId !== folderId) return;
    if (!target || item.id === target.id) return;
    const siblings = items.filter((item) => item.folderId === folderId);
    const from = siblings.findIndex((n) => n.id === item.id);
    const to = siblings.findIndex((n) => n.id === target.id);
    siblings.splice(to, 0, ...siblings.splice(from, 1));
    const ordered: Array<{ id: string; kind: "category" | "note" }> = siblings.map((n) => ({
      id: n.id,
      kind: "note",
    }));
    if (folderId === null)
      ordered.push(...folders.map((f) => ({ id: f.id, kind: "category" as const })));
    await options.onReorder(folderId, ordered);
  };
  return (
    <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
      <DndContext
        sensors={sensors}
        collisionDetection={(args) => {
          const activeItem = items.find((item) => item.id === args.active.id);
          if (!activeItem) return [];
          const ids = new Set(
            items.filter((item) => item.folderId === activeItem.folderId).map((item) => item.id),
          );
          return closestCenter({
            ...args,
            droppableContainers: args.droppableContainers.filter((container) =>
              ids.has(String(container.id)),
            ),
          });
        }}
        onDragEnd={(event) => void onDragEnd(event)}
      >
        <ProjectFolderGroups
          folders={folders}
          items={items}
          onFolderSelect={options.onCategorySelect}
          renderGroup={(folderId, content) => (
            <SortableContext
              items={items.filter((item) => item.folderId === folderId).map((item) => item.id)}
              strategy={verticalListSortingStrategy}
            >
              {content}
            </SortableContext>
          )}
          getFolderHeaderProps={(folder) => ({
            isRenaming: options.renamingId === folder.id,
            onRenameConfirm: (title) => options.onRenameConfirm(folder.id, "category", title),
            onRenameCancel: options.onRenameCancel,
            onContextMenu: (e) => {
              e.preventDefault();
              options.onContextMenu(
                folder.id,
                "category",
                { x: e.clientX, y: e.clientY },
                folder.title,
              );
            },
          })}
          renderFolderMenu={(folder) => (
            <IconButton
              variant="ghost"
              size="1"
              aria-label={t("common.more")}
              onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                options.onCategorySelect(folder.id);
                options.onContextMenu(
                  folder.id,
                  "category",
                  { x: r.left, y: r.bottom },
                  folder.title,
                );
              }}
            >
              <MoreHorizontal size={14} />
            </IconButton>
          )}
          renderItem={(note) => (
            <NoteRow
              key={note.id}
              note={note}
              options={options}
            />
          )}
        />
        {items.length === 0 && folders.length === 0 && (
          <div style={{ padding: 18, color: "var(--gray-11)" }}>{options.emptyLabel}</div>
        )}
      </DndContext>
    </div>
  );
}
