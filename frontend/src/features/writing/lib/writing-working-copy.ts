export interface TimestampedWritingWorkingCopy {
  updatedAt: Date;
}

export interface WritingWorkingCopyDraft {
  title: string;
  content: string;
}

export interface RemoteWritingEntity extends WritingWorkingCopyDraft {
  updatedAt: string;
}

export interface LocalWritingWorkingCopy extends WritingWorkingCopyDraft {
  baseUpdatedAt: string;
  baseTitle?: string;
  baseContent?: string;
  updatedAt: Date;
}

export interface WritingWorkingCopyConflict {
  local: LocalWritingWorkingCopy;
  remote: RemoteWritingEntity;
}

function getTimestamp(value: string): number {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export function isRemoteWritingEntityNewer(
  remoteUpdatedAt: string,
  currentUpdatedAt: string,
): boolean {
  return getTimestamp(remoteUpdatedAt) > getTimestamp(currentUpdatedAt);
}

export function getNextWritingWorkingCopyTimestamp(current: Date): Date {
  return new Date(Math.max(Date.now(), current.getTime() + 1));
}

export function isWritingWorkingCopyNewer(
  workingCopy: TimestampedWritingWorkingCopy,
  remoteUpdatedAt: string,
): boolean {
  return workingCopy.updatedAt.getTime() > getTimestamp(remoteUpdatedAt);
}

export function shouldReplaceWritingWorkingCopy(
  next: TimestampedWritingWorkingCopy,
  current: TimestampedWritingWorkingCopy | undefined,
): boolean {
  return !current || next.updatedAt.getTime() >= current.updatedAt.getTime();
}

export function shouldDeleteWritingWorkingCopy(
  workingCopy: TimestampedWritingWorkingCopy,
  remoteUpdatedAt: string,
): boolean {
  return !isWritingWorkingCopyNewer(workingCopy, remoteUpdatedAt);
}

export function areWritingWorkingCopyDraftsEqual(
  left: WritingWorkingCopyDraft,
  right: WritingWorkingCopyDraft,
): boolean {
  return left.title === right.title && left.content === right.content;
}

export function resolveWritingWorkingCopy(
  remote: RemoteWritingEntity,
  workingCopy: LocalWritingWorkingCopy | null,
): {
  draft: WritingWorkingCopyDraft;
  shouldDelete: boolean;
  conflict?: WritingWorkingCopyConflict;
} {
  if (workingCopy && !areWritingWorkingCopyDraftsEqual(workingCopy, remote)) {
    const hasContentBase =
      typeof workingCopy.baseTitle === "string" && typeof workingCopy.baseContent === "string";
    const remoteMatchesBase =
      hasContentBase &&
      workingCopy.baseTitle === remote.title &&
      workingCopy.baseContent === remote.content;
    const hasUnchangedTimestamp = workingCopy.baseUpdatedAt === remote.updatedAt;

    if (
      hasContentBase &&
      areWritingWorkingCopyDraftsEqual(workingCopy, {
        title: workingCopy.baseTitle!,
        content: workingCopy.baseContent!,
      })
    ) {
      return { draft: { title: remote.title, content: remote.content }, shouldDelete: true };
    }
    if (remoteMatchesBase || (!hasContentBase && hasUnchangedTimestamp)) {
      return {
        draft: { title: workingCopy.title, content: workingCopy.content },
        shouldDelete: false,
      };
    }

    return {
      draft: { title: workingCopy.title, content: workingCopy.content },
      shouldDelete: false,
      conflict: {
        local: workingCopy,
        remote: { title: remote.title, content: remote.content, updatedAt: remote.updatedAt },
      },
    };
  }

  return {
    draft: { title: remote.title, content: remote.content },
    shouldDelete: workingCopy !== null,
  };
}
