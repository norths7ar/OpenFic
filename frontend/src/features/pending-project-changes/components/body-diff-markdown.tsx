import { createContext, useContext } from "react";
import { useTranslation } from "react-i18next";
import { Block, type BlockProps } from "streamdown";

import { StreamingMarkdown } from "@/components/streaming-markdown";

import type { BlockChange } from "./body-diff";

const ChangeContext = createContext<readonly BlockChange[]>([]);

function ReviewBlock(props: BlockProps) {
  const changes = useContext(ChangeContext);
  const { t } = useTranslation();
  const change = changes[props.index] ?? "unchanged";
  if (!props.content.trim()) return <Block {...props} />;
  return (
    <div className={`pending-body-block pending-body-block--${change}`}>
      {change !== "unchanged" && (
        <span className="pending-body-block-label">
          {t(`pendingProjectChanges.blockChanges.${change}`)}
        </span>
      )}
      <Block {...props} />
    </div>
  );
}

export function BodyDiffMarkdown({
  content,
  changes,
}: {
  content: string;
  changes: readonly BlockChange[];
}) {
  return (
    <ChangeContext.Provider value={changes}>
      <StreamingMarkdown
        content={content}
        BlockComponent={ReviewBlock}
      />
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
