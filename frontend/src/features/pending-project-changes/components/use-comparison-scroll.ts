import { useEffect, useRef } from "react";

/** Wheel outside the two versions moves both without destroying their offset. */
export function useComparisonScroll(changeId?: string) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.shiftKey || !event.deltaY || !(event.target instanceof Element))
        return;
      const target = event.target;
      if (target.closest("input, textarea, select, [role=combobox], details")) return;
      // Let the browser handle the hovered body's own scrolling and text editing.
      if (target.closest(".pending-project-changes-body-version-content")) return;
      const version = target.closest(".pending-project-changes-body-version");
      const panes = (version ?? root).querySelectorAll<HTMLElement>(
        ".pending-project-changes-body-version-content",
      );
      let moved = false;
      for (const container of panes) {
        const pane = container.querySelector("textarea") ?? container;
        const unit = event.deltaMode === 2 ? pane.clientHeight : event.deltaMode === 1 ? 16 : 1;
        const previous = pane.scrollTop;
        pane.scrollTop += event.deltaY * unit;
        moved ||= pane.scrollTop !== previous;
      }
      if (moved) event.preventDefault();
    };
    root.addEventListener("wheel", onWheel, { passive: false });
    return () => root.removeEventListener("wheel", onWheel);
  }, [changeId]);
  return ref;
}
