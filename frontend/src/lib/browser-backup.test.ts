import { describe, expect, it } from "vitest";

import { parseBrowserBackupJson } from "./browser-backup";

function validBackup(): Record<string, unknown> {
  return {
    format: "openfic-browser-backup",
    version: 1,
    exportedAt: "2026-09-08T00:00:00.000Z",
    database: {
      name: "OpenFicDB",
      tables: {
        projectLastChapters: [
          { projectId: "project-1", chapterId: "chapter-1", updatedAt: "2026-09-08T00:00:00Z" },
        ],
        projectTabs: [
          {
            projectId: "project-1",
            tabs: [
              {
                id: "tab-1",
                chapterId: "chapter-1",
                title: "Chapter",
                isLocked: false,
              },
            ],
            activeTabId: "tab-1",
            updatedAt: "2026-09-08T00:00:00Z",
          },
        ],
        userPreferences: [
          { key: "openfic-language", value: "en", updatedAt: "2026-09-08T00:00:00Z" },
        ],
        promptChainWorkingCopies: [
          {
            chainId: "chain-1",
            baseVersionId: "version-1",
            entries: [
              {
                id: "entry-1",
                name: "System",
                role: "system",
                content: "Draft",
                order_index: 0,
                is_enabled: true,
                token_count: 1,
              },
            ],
            updatedAt: "2026-09-08T00:00:00Z",
          },
        ],
        writingWorkingCopies: [
          {
            id: "chapter:chapter-1",
            entityId: "chapter-1",
            type: "chapter",
            title: "Draft chapter",
            content: "Uncommitted content",
            baseUpdatedAt: "2026-09-08T00:00:00Z",
            updatedAt: "2026-09-08T00:01:00Z",
          },
        ],
        agentInputHistories: [
          {
            projectId: "project-1",
            entries: ["Earlier prompt"],
            draft: "Unsent prompt",
            updatedAt: "2026-09-08T00:00:00Z",
          },
        ],
        recentProjects: [
          {
            slot: 0,
            projectId: "project-1",
            title: "Project",
            color: "blue",
            openedAt: "2026-09-08T00:00:00Z",
          },
        ],
      },
    },
    localStorage: {
      "openfic-language": "en",
      "openfic.appSidebar.expanded": "true",
    },
  };
}

describe("browser backup format", () => {
  it("keeps records, dates, and original working-copy IDs", () => {
    const backup = parseBrowserBackupJson(JSON.stringify(validBackup()));

    expect(backup.database.tables.writingWorkingCopies[0]).toMatchObject({
      id: "chapter:chapter-1",
      entityId: "chapter-1",
    });
    expect(backup.database.tables.writingWorkingCopies[0]?.updatedAt).toBeInstanceOf(Date);
    expect(backup.localStorage).toEqual({
      "openfic-language": "en",
      "openfic.appSidebar.expanded": "true",
    });
  });

});
