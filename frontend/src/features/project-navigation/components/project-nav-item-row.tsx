import type { ComponentProps, ReactNode } from "react";

import { PROJECT_NAV_ITEM_HEIGHT } from "../lib/project-nav-layout";

import "./project-nav.css";

interface ProjectNavItemRowProps extends Omit<ComponentProps<"div">, "title"> {
  title: ReactNode;
  metadata: ReactNode;
  status?: ReactNode;
  actions?: ReactNode;
  leading?: ReactNode;
  selected?: boolean;
  disabled?: boolean;
  dragging?: boolean;
}

/** Two-line chapter layout shared by every project navigation item. */
export function ProjectNavItemRow({
  title,
  metadata,
  status,
  actions,
  leading,
  selected,
  disabled,
  dragging,
  style,
  className = "",
  ...props
}: ProjectNavItemRowProps) {
  return (
    <div
      {...props}
      style={{ minHeight: PROJECT_NAV_ITEM_HEIGHT, ...style }}
      className={`project-nav-item-row ${className}`}
      data-selected={selected || undefined}
      aria-disabled={disabled || undefined}
      data-dragging={dragging || undefined}
    >
      <div className="project-nav-item-leading">{leading}</div>
      <div className="project-nav-item-text">
        <div className="project-nav-item-heading">
          <div className="project-nav-item-title">{title}</div>
          {status}
        </div>
        <div className="project-nav-item-metadata">{metadata}</div>
      </div>
      {actions && <div className="project-nav-item-actions">{actions}</div>}
    </div>
  );
}
