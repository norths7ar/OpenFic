import { db, flushBrowserBackupWrites } from "./local-db";

const BACKUP_FORMAT = "openfic-browser-backup";
const BACKUP_VERSION = 1;

export const BROWSER_BACKUP_TABLE_NAMES = [
  "projectLastChapters",
  "projectTabs",
  "userPreferences",
  "promptChainWorkingCopies",
  "writingWorkingCopies",
  "agentInputHistories",
  "recentProjects",
] as const;

export const BROWSER_BACKUP_LOCAL_STORAGE_KEYS = [
  "openfic-language",
  "openfic.project-nav-width-px",
  "openfic.project-nav-width",
  "openfic.appSidebar.lastProjectId",
  "openfic.appSidebar.expanded",
  "openfic.agent.selectedModelId",
  "openfic.agent.selectedAgentKey",
  "openfic.agent.reasoningEffort",
] as const;

const BROWSER_BACKUP_CONTENT_TABLE_NAMES = [
  "projectLastChapters",
  "projectTabs",
  "promptChainWorkingCopies",
  "writingWorkingCopies",
  "agentInputHistories",
  "recentProjects",
] as const;

type BrowserBackupTableName = (typeof BROWSER_BACKUP_TABLE_NAMES)[number];

export interface BrowserBackup {
  format: typeof BACKUP_FORMAT;
  version: typeof BACKUP_VERSION;
  exportedAt: string;
  database: {
    name: "OpenFicDB";
    tables: Record<BrowserBackupTableName, unknown[]>;
  };
  localStorage: Record<string, string>;
}

export class BrowserBackupError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BrowserBackupError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value) {
    throw new BrowserBackupError(`${label} must be a non-empty string.`);
  }
  return value;
}

function requireText(value: unknown, label: string): string {
  if (typeof value !== "string") {
    throw new BrowserBackupError(`${label} must be a string.`);
  }
  return value;
}

function requireDate(value: unknown, label: string): Date {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) {
    throw new BrowserBackupError(`${label} must be a valid date string.`);
  }
  return new Date(value);
}

function requireBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") {
    throw new BrowserBackupError(`${label} must be a boolean.`);
  }
  return value;
}

function requireStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    throw new BrowserBackupError(`${label} must be an array of strings.`);
  }
  return value;
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new BrowserBackupError(`${label} must be an object.`);
  return value;
}

function requireTableKeys(tables: Record<string, unknown>): void {
  const expected = new Set<string>(BROWSER_BACKUP_TABLE_NAMES);
  const actual = Object.keys(tables);
  if (actual.length !== expected.size || actual.some((name) => !expected.has(name))) {
    throw new BrowserBackupError("Backup tables do not match this OpenFic browser format.");
  }
  for (const name of BROWSER_BACKUP_TABLE_NAMES) {
    if (!Array.isArray(tables[name])) {
      throw new BrowserBackupError(`Backup table ${name} must be an array.`);
    }
  }
}

function validateProjectLastChapter(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "projectLastChapters record");
  requireString(value.projectId, "projectLastChapters.projectId");
  requireString(value.chapterId, "projectLastChapters.chapterId");
  value.updatedAt = requireDate(value.updatedAt, "projectLastChapters.updatedAt");
  return value;
}

function validateProjectTabs(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "projectTabs record");
  requireString(value.projectId, "projectTabs.projectId");
  value.updatedAt = requireDate(value.updatedAt, "projectTabs.updatedAt");
  if (!Array.isArray(value.tabs))
    throw new BrowserBackupError("projectTabs.tabs must be an array.");
  for (const tab of value.tabs) {
    const tabValue = requireRecord(tab, "projectTabs.tabs record");
    requireString(tabValue.id, "projectTabs.tabs.id");
    requireText(tabValue.title, "projectTabs.tabs.title");
    requireBoolean(tabValue.isLocked, "projectTabs.tabs.isLocked");
    if (tabValue.chapterId != null) requireString(tabValue.chapterId, "projectTabs.tabs.chapterId");
    if (tabValue.refId != null) requireString(tabValue.refId, "projectTabs.tabs.refId");
  }
  if (value.activeTabId != null) requireString(value.activeTabId, "projectTabs.activeTabId");
  return value;
}

function validateUserPreference(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "userPreferences record");
  requireString(value.key, "userPreferences.key");
  if (typeof value.value !== "string") {
    throw new BrowserBackupError("userPreferences.value must be a string.");
  }
  value.updatedAt = requireDate(value.updatedAt, "userPreferences.updatedAt");
  return value;
}

function validatePromptChainWorkingCopy(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "promptChainWorkingCopies record");
  requireString(value.chainId, "promptChainWorkingCopies.chainId");
  requireString(value.baseVersionId, "promptChainWorkingCopies.baseVersionId");
  if (!Array.isArray(value.entries)) {
    throw new BrowserBackupError("promptChainWorkingCopies.entries must be an array.");
  }
  for (const entry of value.entries) {
    const entryValue = requireRecord(entry, "promptChainWorkingCopies.entries record");
    requireText(entryValue.name, "promptChainWorkingCopies.entries.name");
    requireText(entryValue.content, "promptChainWorkingCopies.entries.content");
    if (!["system", "user", "assistant"].includes(String(entryValue.role))) {
      throw new BrowserBackupError("promptChainWorkingCopies.entries.role is invalid.");
    }
    if (!Number.isFinite(entryValue.order_index) || !Number.isFinite(entryValue.token_count)) {
      throw new BrowserBackupError(
        "promptChainWorkingCopies entry order and token count must be numbers.",
      );
    }
    requireBoolean(entryValue.is_enabled, "promptChainWorkingCopies.entries.is_enabled");
    if (entryValue.id != null) requireString(entryValue.id, "promptChainWorkingCopies.entries.id");
    if (entryValue.uid != null)
      requireString(entryValue.uid, "promptChainWorkingCopies.entries.uid");
  }
  value.updatedAt = requireDate(value.updatedAt, "promptChainWorkingCopies.updatedAt");
  return value;
}

function validateWritingWorkingCopy(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "writingWorkingCopies record");
  const entityId = requireString(value.entityId, "writingWorkingCopies.entityId");
  const type = requireString(value.type, "writingWorkingCopies.type");
  if (type !== "chapter" && type !== "note") {
    throw new BrowserBackupError("writingWorkingCopies.type is invalid.");
  }
  if (value.id !== `${type}:${entityId}`) {
    throw new BrowserBackupError("writingWorkingCopies.id does not match its original entity ID.");
  }
  requireText(value.title, "writingWorkingCopies.title");
  requireText(value.content, "writingWorkingCopies.content");
  requireDate(value.baseUpdatedAt, "writingWorkingCopies.baseUpdatedAt");
  value.updatedAt = requireDate(value.updatedAt, "writingWorkingCopies.updatedAt");
  return value;
}

function validateAgentInputHistory(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "agentInputHistories record");
  requireString(value.projectId, "agentInputHistories.projectId");
  requireStringArray(value.entries, "agentInputHistories.entries");
  if (typeof value.draft !== "string") {
    throw new BrowserBackupError("agentInputHistories.draft must be a string.");
  }
  value.updatedAt = requireDate(value.updatedAt, "agentInputHistories.updatedAt");
  return value;
}

function validateRecentProject(record: unknown): Record<string, unknown> {
  const value = requireRecord(record, "recentProjects record");
  if (!Number.isInteger(value.slot) || Number(value.slot) < 0 || Number(value.slot) > 2) {
    throw new BrowserBackupError("recentProjects.slot must be between 0 and 2.");
  }
  requireString(value.projectId, "recentProjects.projectId");
  requireText(value.title, "recentProjects.title");
  if (!["blue", "green", "orange", "purple", "teal", "pink"].includes(String(value.color))) {
    throw new BrowserBackupError("recentProjects.color is invalid.");
  }
  value.openedAt = requireDate(value.openedAt, "recentProjects.openedAt");
  return value;
}

const TABLE_VALIDATORS: Record<
  BrowserBackupTableName,
  (record: unknown) => Record<string, unknown>
> = {
  projectLastChapters: validateProjectLastChapter,
  projectTabs: validateProjectTabs,
  userPreferences: validateUserPreference,
  promptChainWorkingCopies: validatePromptChainWorkingCopy,
  writingWorkingCopies: validateWritingWorkingCopy,
  agentInputHistories: validateAgentInputHistory,
  recentProjects: validateRecentProject,
};

const TABLE_PRIMARY_KEYS: Record<BrowserBackupTableName, string> = {
  projectLastChapters: "projectId",
  projectTabs: "projectId",
  userPreferences: "key",
  promptChainWorkingCopies: "chainId",
  writingWorkingCopies: "id",
  agentInputHistories: "projectId",
  recentProjects: "slot",
};

function requireUniquePrimaryKeys(
  name: BrowserBackupTableName,
  records: Record<string, unknown>[],
) {
  const primaryKey = TABLE_PRIMARY_KEYS[name];
  const keys = new Set<unknown>();
  for (const record of records) {
    const value = record[primaryKey];
    if (keys.has(value)) {
      throw new BrowserBackupError(`Backup table ${name} contains duplicate original IDs.`);
    }
    keys.add(value);
  }
}

function parseBrowserBackup(value: unknown): BrowserBackup {
  const backup = requireRecord(value, "Browser backup");
  if (backup.format !== BACKUP_FORMAT || backup.version !== BACKUP_VERSION) {
    throw new BrowserBackupError("This file is not a supported OpenFic browser backup.");
  }
  requireDate(backup.exportedAt, "exportedAt");
  const database = requireRecord(backup.database, "database");
  if (database.name !== "OpenFicDB") {
    throw new BrowserBackupError("Backup database name is not OpenFicDB.");
  }
  const sourceTables = requireRecord(database.tables, "database.tables");
  requireTableKeys(sourceTables);
  const tables = {} as Record<BrowserBackupTableName, unknown[]>;
  for (const name of BROWSER_BACKUP_TABLE_NAMES) {
    const records = sourceTables[name];
    if (!Array.isArray(records)) {
      throw new BrowserBackupError(`Backup table ${name} must be an array.`);
    }
    const validatedRecords = records.map(TABLE_VALIDATORS[name]);
    requireUniquePrimaryKeys(name, validatedRecords);
    tables[name] = validatedRecords;
  }

  const sourceStorage = requireRecord(backup.localStorage, "localStorage");
  const storage: Record<string, string> = {};
  for (const [key, item] of Object.entries(sourceStorage)) {
    if (!BROWSER_BACKUP_LOCAL_STORAGE_KEYS.includes(key as never) || typeof item !== "string") {
      throw new BrowserBackupError("Backup contains an unsupported local storage preference.");
    }
    storage[key] = item;
  }

  return {
    format: BACKUP_FORMAT,
    version: BACKUP_VERSION,
    exportedAt: String(backup.exportedAt),
    database: { name: "OpenFicDB", tables },
    localStorage: storage,
  };
}

export function parseBrowserBackupJson(json: string): BrowserBackup {
  try {
    return parseBrowserBackup(JSON.parse(json) as unknown);
  } catch (error) {
    if (error instanceof BrowserBackupError) throw error;
    throw new BrowserBackupError("Backup file is not valid JSON.");
  }
}

async function readBackupTables(): Promise<Record<BrowserBackupTableName, unknown[]>> {
  return db.transaction(
    "r",
    BROWSER_BACKUP_TABLE_NAMES.map((name) => db.table(name)),
    async () => {
      const tableEntries = await Promise.all(
        BROWSER_BACKUP_TABLE_NAMES.map(
          async (name) => [name, await db.table(name).toArray()] as const,
        ),
      );
      return Object.fromEntries(tableEntries) as Record<BrowserBackupTableName, unknown[]>;
    },
  );
}

function readOwnedLocalStorage(): Record<string, string> {
  const values: Record<string, string> = {};
  for (const key of BROWSER_BACKUP_LOCAL_STORAGE_KEYS) {
    const value = window.localStorage.getItem(key);
    if (value !== null) values[key] = value;
  }
  return values;
}

export async function createBrowserBackup(): Promise<BrowserBackup> {
  await flushBrowserBackupWrites();
  await db.open();
  return {
    format: BACKUP_FORMAT,
    version: BACKUP_VERSION,
    exportedAt: new Date().toISOString(),
    database: {
      name: "OpenFicDB",
      tables: await readBackupTables(),
    },
    localStorage: readOwnedLocalStorage(),
  };
}

export async function isBrowserBackupTargetEmpty(): Promise<boolean> {
  await db.open();
  const tableCounts = await Promise.all(
    BROWSER_BACKUP_CONTENT_TABLE_NAMES.map((name) => db.table(name).count()),
  );
  return tableCounts.every((count) => count === 0);
}

export async function restoreBrowserBackup(backup: BrowserBackup): Promise<void> {
  if (!(await isBrowserBackupTargetEmpty())) {
    throw new BrowserBackupError(
      "Browser restore only works in a new, empty OpenFic browser profile and will not overwrite data.",
    );
  }

  await db.transaction(
    "rw",
    BROWSER_BACKUP_TABLE_NAMES.map((name) => db.table(name)),
    async () => {
      const contentCounts = await Promise.all(
        BROWSER_BACKUP_CONTENT_TABLE_NAMES.map((name) => db.table(name).count()),
      );
      if (contentCounts.some((count) => count > 0)) {
        throw new BrowserBackupError(
          "Browser restore only works in a new OpenFic browser profile and will not overwrite content.",
        );
      }
      for (const name of BROWSER_BACKUP_TABLE_NAMES) {
        const table = db.table(name);
        await table.clear();
        const records = backup.database.tables[name];
        if (records.length > 0) await table.bulkPut(records);
      }
    },
  );

  for (const [key, value] of Object.entries(backup.localStorage)) {
    window.localStorage.setItem(key, value);
  }
}

export function browserBackupFileName(exportedAt = new Date()): string {
  return `openfic-browser-backup-${exportedAt.toISOString().replaceAll(/[:.]/g, "-")}.json`;
}

export function downloadBrowserBackup(backup: BrowserBackup): void {
  const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = browserBackupFileName(new Date(backup.exportedAt));
  link.click();
  URL.revokeObjectURL(url);
}
