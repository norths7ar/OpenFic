import { Circle, Sparkles, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { useAgentVisibilityCatalog } from "@/hooks/use-agent-visibility-catalog";

import "./agent-visibility-button.css";

// Presentation only: available states and cycling order still come from the catalog.
const stateIcons: Record<string, typeof Circle> = { all: Circle, global: Sparkles, none: X };

export function AgentVisibilityButton({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const { data, isError } = useAgentVisibilityCatalog();
  const states = data?.states ?? [];
  const index = states.findIndex((state) => state.value === value);
  const current = states[index];
  const next = states[(index + 1) % states.length];
  const unavailable = isError || (data !== undefined && !current);
  const label = unavailable ? "不可用" : (current?.label ?? "…");
  const description = isError
    ? "知识可见范围加载失败，请刷新后重试"
    : unavailable
      ? "当前资料状态不在知识可见范围目录中，请刷新后重试"
      : current && next
        ? `${current.description}；点击切换为${next.label}`
        : "正在加载知识可见范围";
  const isDisabled = disabled || unavailable || !current || !next;
  const StateIcon = stateIcons[value] ?? Circle;
  return (
    <motion.button
      type="button"
      className="agent-visibility-button"
      data-visibility={unavailable ? "unavailable" : value}
      aria-label={`资料可见性：${label}`}
      title={description}
      disabled={isDisabled}
      whileHover={!isDisabled && !reduceMotion ? { y: -1 } : undefined}
      whileTap={!isDisabled && !reduceMotion ? { scale: 0.94, y: 0 } : undefined}
      transition={{ type: "spring", stiffness: 500, damping: 28 }}
      onPointerDown={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        if (!unavailable && next) onChange(next.value);
      }}
    >
      <AnimatePresence initial={false} mode="popLayout">
        <motion.span
          key={label}
          className="agent-visibility-button__content"
          initial={reduceMotion ? false : { opacity: 0, y: 5, scale: 0.92 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -5, scale: 0.92 }}
          transition={{ duration: reduceMotion ? 0 : 0.18, ease: "easeOut" }}
          aria-hidden="true"
        >
          <span className="agent-visibility-button__symbol" data-symbol={value}>
            <StateIcon size={11} strokeWidth={2} />
          </span>
          <span className="agent-visibility-button__label">{label}</span>
        </motion.span>
      </AnimatePresence>
    </motion.button>
  );
}
