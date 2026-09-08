import { useAgentVisibilityCatalog } from "@/hooks/use-agent-visibility-catalog";

export function AgentVisibilityButton({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
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
  return (
    <button
      type="button"
      className="agent-visibility-button"
      aria-label={`资料可见性：${label}`}
      title={description}
      disabled={disabled || unavailable || !current || !next}
      onPointerDown={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        if (!unavailable && next) onChange(next.value);
      }}
      style={{
        width: 56,
        minWidth: 56,
        height: 24,
        padding: "0 4px",
        border: "1px solid var(--gray-a5)",
        borderRadius: 5,
        background: "var(--gray-a2)",
        color: "var(--gray-11)",
        fontSize: 11,
        cursor: disabled ? "default" : "pointer",
      }}
    >
      {label}
    </button>
  );
}
