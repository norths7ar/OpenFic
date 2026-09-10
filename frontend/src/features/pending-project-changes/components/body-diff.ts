import { diffArrays } from "diff";
import { parseMarkdownIntoBlocks } from "streamdown";

export type BlockChange = "unchanged" | "added" | "changed" | "removed";

// Use the renderer's block boundaries: lists, tables and code fences stay intact.
export function compareBodyBlocks(before: string, after: string) {
  const left = parseMarkdownIntoBlocks(before);
  const right = parseMarkdownIntoBlocks(after);
  const beforeChanges: BlockChange[] = [];
  const afterChanges: BlockChange[] = [];
  const chunks = diffArrays(
    left.filter((block) => block.trim()),
    right.filter((block) => block.trim()),
  );
  for (let index = 0; index < chunks.length; index++) {
    const chunk = chunks[index];
    if (!chunk.added && !chunk.removed) {
      beforeChanges.push(...chunk.value.map(() => "unchanged" as const));
      afterChanges.push(...chunk.value.map(() => "unchanged" as const));
    } else if (chunk.removed && chunks[index + 1]?.added) {
      const added = chunks[++index];
      const replacement = alignReplacementBlocks(chunk.value, added.value);
      beforeChanges.push(...replacement.before);
      afterChanges.push(...replacement.after);
    } else if (chunk.removed) {
      beforeChanges.push(...chunk.value.map(() => "removed" as const));
    } else {
      afterChanges.push(...chunk.value.map(() => "added" as const));
    }
  }
  let leftIndex = 0;
  let rightIndex = 0;
  return {
    before: left.map((block) =>
      block.trim() ? beforeChanges[leftIndex++] : ("unchanged" as const),
    ),
    after: right.map((block) =>
      block.trim() ? afterChanges[rightIndex++] : ("unchanged" as const),
    ),
  };
}

function blockKind(block: string) {
  const text = block.trimStart();
  if (/^(?:`{3,}|~{3,})/.test(text)) return "code";
  if (/^#{1,6}\s/.test(text) || /\n(?:=+|-+)\s*$/.test(text)) return "heading";
  if (/^(?:[-+*]|\d+[.)])\s/.test(text)) return "list";
  if (/^>/.test(text)) return "quote";
  if (/^.*\|.*\n\s*\|?\s*:?-{3}/.test(text)) return "table";
  return "paragraph";
}

// Exact unchanged blocks anchor the outer diff. Within a changed run, prefer
// structural blocks over generic paragraphs so insertions do not shift tables/lists.
function alignReplacementBlocks(before: string[], after: string[]) {
  const left = before.map(blockKind);
  const right = after.map(blockKind);
  const scores = Array.from({ length: left.length + 1 }, () => new Uint32Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i--) {
    for (let j = right.length - 1; j >= 0; j--) {
      const match =
        left[i] === right[j] ? scores[i + 1][j + 1] + (left[i] === "paragraph" ? 1 : 3) : 0;
      scores[i][j] = Math.max(match, scores[i + 1][j], scores[i][j + 1]);
    }
  }
  const result: { before: BlockChange[]; after: BlockChange[] } = { before: [], after: [] };
  let i = 0,
    j = 0;
  while (i < left.length || j < right.length) {
    if (
      i < left.length &&
      j < right.length &&
      left[i] === right[j] &&
      scores[i][j] === scores[i + 1][j + 1] + (left[i] === "paragraph" ? 1 : 3)
    ) {
      result.before.push("changed");
      result.after.push("changed");
      i++;
      j++;
    } else if (j < right.length && (i === left.length || scores[i][j + 1] >= scores[i + 1][j])) {
      result.after.push("added");
      j++;
    } else {
      result.before.push("removed");
      i++;
    }
  }
  return result;
}
