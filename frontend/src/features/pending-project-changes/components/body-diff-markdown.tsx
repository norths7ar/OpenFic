import { createContext, useContext, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Block, type BlockProps } from "streamdown";

import { StreamingMarkdown } from "@/components/streaming-markdown";

import type { BlockChange, CharacterRange } from "./body-diff";
import { characterHighlightPlugin } from "./body-diff-highlight";

const ChangeContext = createContext<readonly BlockChange[]>([]);
const HighlightContext = createContext<{
  ranges: readonly (readonly CharacterRange[])[];
  side: "before" | "after";
}>({ ranges: [], side: "after" });

function ReviewBlock(props: BlockProps) {
  const changes = useContext(ChangeContext);
  const { t } = useTranslation();
  const change = changes[props.index] ?? "unchanged";
  const { ranges, side } = useContext(HighlightContext);
  const rehypePlugins = useMemo<BlockProps["rehypePlugins"]>(
    () => [
      ...(props.rehypePlugins ?? []),
      // Streamdown caches processors by plugin name and serialized options.
      // Keep per-block inputs in options, not in an indistinguishable closure.
      [
        characterHighlightPlugin,
        { source: props.content, ranges: ranges[props.index] ?? [], side },
      ],
    ],
    [props.rehypePlugins, props.content, props.index, ranges, side],
  );
  if (!props.content.trim()) return <Block {...props} />;
  return (
    <div className={`pending-body-block pending-body-block--${change}`}>
      {change !== "unchanged" && (
        <span className="pending-body-block-label">
          {t(`pendingProjectChanges.blockChanges.${change}`)}
        </span>
      )}
      <Block
        {...props}
        rehypePlugins={rehypePlugins}
      />
    </div>
  );
}

export function BodyDiffMarkdown({
  content,
  changes,
  ranges = [],
  side = "after",
}: {
  content: string;
  changes: readonly BlockChange[];
  ranges?: readonly (readonly CharacterRange[])[];
  side?: "before" | "after";
}) {
  const highlights = useMemo(() => ({ ranges, side }), [ranges, side]);
  return (
    <ChangeContext.Provider value={changes}>
      <HighlightContext.Provider value={highlights}>
        <StreamingMarkdown
          content={content}
          BlockComponent={ReviewBlock}
        />
      </HighlightContext.Provider>
    </ChangeContext.Provider>
  );
}

export function BodyDiffLegend() {
  const { t } = useTranslation();
  return (
    <div className="pending-body-legend">
      {(["added", "changed", "removed"] as const).map((change) => (
        <span
          key={change}
          className={`pending-body-legend-item pending-body-block--${change}`}
        >
          {t(`pendingProjectChanges.blockChanges.${change}`)}
        </span>
      ))}
    </div>
  );
}
