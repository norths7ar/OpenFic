import { useRef, useState, type ReactNode } from "react";

import {
  PROJECT_NAV_MAX_WIDTH,
  PROJECT_NAV_MIN_WIDTH,
  useProjectNavWidth,
} from "../hooks/use-project-nav-width";

import "./project-nav.css";

interface ProjectNavShellProps {
  children: ReactNode;
  toolbar?: ReactNode;
  className?: string;
  label?: string;
}

/** Owns the project navigation width; workspace/editor panels remain outside it. */
export function ProjectNavShell({
  children,
  toolbar,
  className = "",
  label = "项目导航",
}: ProjectNavShellProps) {
  const { width, setWidth } = useProjectNavWidth();
  const origin = useRef<{ x: number; width: number } | null>(null);
  const [resizing, setResizing] = useState(false);

  return (
    <aside
      className={`project-nav-shell ${className}`}
      style={{ width }}
      aria-label={label}
    >
      {toolbar}
      <div className="project-nav-shell-content">{children}</div>
      <div
        className="project-nav-separator"
        role="separator"
        tabIndex={0}
        aria-label={label}
        aria-orientation="vertical"
        aria-valuemin={PROJECT_NAV_MIN_WIDTH}
        aria-valuemax={PROJECT_NAV_MAX_WIDTH}
        aria-valuenow={width}
        data-resizing={resizing || undefined}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          origin.current = { x: event.clientX, width };
          event.currentTarget.setPointerCapture(event.pointerId);
          setResizing(true);
        }}
        onPointerMove={(event) => {
          if (origin.current) setWidth(origin.current.width + event.clientX - origin.current.x);
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
          origin.current = null;
          setResizing(false);
        }}
        onLostPointerCapture={() => {
          origin.current = null;
          setResizing(false);
        }}
        onKeyDown={(event) => {
          const next =
            event.key === "ArrowLeft"
              ? width - 10
              : event.key === "ArrowRight"
                ? width + 10
                : event.key === "Home"
                  ? PROJECT_NAV_MIN_WIDTH
                  : event.key === "End"
                    ? PROJECT_NAV_MAX_WIDTH
                    : null;
          if (next === null) return;
          event.preventDefault();
          setWidth(next);
        }}
      />
    </aside>
  );
}
