import type { CharacterRange } from "./body-diff";

type HtmlNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  position?: { start: { offset?: number }; end: { offset?: number } };
  children?: HtmlNode[];
};

// Mark rendered text using source positions, without splitting Markdown syntax.
// Transformed text (entities, escapes, math/code) keeps the block-level signal
// when its rendered offsets cannot be mapped back to the source unambiguously.
export function characterHighlightPlugin({
  source,
  ranges,
  side,
}: {
  source: string;
  ranges: readonly CharacterRange[];
  side: "before" | "after";
}) {
  return (tree: HtmlNode) => {
    function visit(parent: HtmlNode) {
      if (
        !parent.children ||
        parent.tagName === "code" ||
        parent.tagName === "pre" ||
        parent.tagName === "svg" ||
        parent.tagName === "math"
      )
        return;
      parent.children = parent.children.flatMap((node): HtmlNode[] => {
        if (node.type !== "text" || typeof node.value !== "string") {
          visit(node);
          return [node];
        }
        const start = node.position?.start.offset;
        const end = node.position?.end.offset;
        if (start === undefined || end === undefined || source.slice(start, end) !== node.value) {
          return [node];
        }
        const overlaps = ranges.filter((range) => range.start < end && range.end > start);
        if (!overlaps.length) return [node];
        const result: HtmlNode[] = [];
        let cursor = start;
        for (const range of overlaps) {
          const from = Math.max(start, range.start);
          const to = Math.min(end, range.end);
          if (from > cursor) result.push({ type: "text", value: source.slice(cursor, from) });
          result.push({
            type: "element",
            tagName: "mark",
            properties: { className: [`pending-body-character--${side}`] },
            children: [{ type: "text", value: source.slice(from, to) }],
          });
          cursor = to;
        }
        if (cursor < end) result.push({ type: "text", value: source.slice(cursor, end) });
        return result;
      });
    }
    visit(tree);
  };
}
