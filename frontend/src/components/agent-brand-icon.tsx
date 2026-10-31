import "./agent-brand-icon.css";
import { getAgentIcon, getAgentIconColor } from "@/lib/agent-branding";

interface AgentBrandIconProps {
  color?: string | null;
  icon?: string | null;
  size?: number;
}

export function AgentBrandIcon({ color, icon, size = 16 }: AgentBrandIconProps) {
  const IconComponent = getAgentIcon(icon);
  return (
    <IconComponent
      size={size}
      aria-hidden="true"
      className="agent-brand-icon__glyph"
      style={{ color: getAgentIconColor(color) }}
    />
  );
}
