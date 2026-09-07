import { useState, type ReactNode } from "react";

import type { ProjectFolder } from "@/features/project-folders/lib/project-folder-api";

import { projectNavGroups, PROJECT_NAV_ROOT_ID } from "../lib/project-nav-groups";
import { ProjectNavGroupHeader, type ProjectNavGroupHeaderProps } from "./project-nav-group-header";

interface FolderedItem {
  id: string;
  folderId: string | null;
}
interface ProjectFolderGroupsProps<T extends FolderedItem> {
  folders: ProjectFolder[];
  items: T[];
  renderItem: (item: T) => ReactNode;
  renderFolderMenu?: (folder: ProjectFolder) => ReactNode;
  getFolderHeaderProps?: (folder: ProjectFolder) => Partial<ProjectNavGroupHeaderProps>;
  onFolderSelect?: (folderId: string) => void;
  renderGroup?: (folderId: string | null, content: ReactNode) => ReactNode;
}

export function ProjectFolderGroups<T extends FolderedItem>({
  folders,
  items,
  renderItem,
  renderFolderMenu,
  getFolderHeaderProps,
  renderGroup,
  onFolderSelect,
}: ProjectFolderGroupsProps<T>) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const groups = projectNavGroups(folders, items, (item) => item.folderId);
  return (
    <div style={{ width: "100%", minWidth: 0 }}>
      {groups.map((group) => {
        const folder = group.folder;
        const groupId = folder?.id ?? PROJECT_NAV_ROOT_ID;
        const children = group.items;
        const content = (
          <>
            {folder && (
              <ProjectNavGroupHeader
                title={folder.title}
                description={folder.description}
                count={children.length}
                isExpanded={!collapsed.has(folder.id)}
                onToggle={() => {
                  onFolderSelect?.(folder.id);
                  setCollapsed((current) => {
                    const next = new Set(current);
                    if (next.has(folder.id)) next.delete(folder.id);
                    else next.add(folder.id);
                    return next;
                  });
                }}
                actions={renderFolderMenu ? renderFolderMenu(folder) : undefined}
                {...(getFolderHeaderProps ? getFolderHeaderProps(folder) : {})}
              />
            )}
            {(!folder || !collapsed.has(folder.id)) && children.map(renderItem)}
          </>
        );
        return (
          <div key={groupId}>
            {renderGroup ? renderGroup(folder?.id ?? null, content) : content}
          </div>
        );
      })}
    </div>
  );
}
