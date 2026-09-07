import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "openfic.project-nav-width-px";
const LEGACY_STORAGE_KEY = "openfic.project-nav-width";
const EVENT_NAME = "openfic:project-nav-width";
export const PROJECT_NAV_MIN_WIDTH = 260;
export const PROJECT_NAV_MAX_WIDTH = 400;
export const PROJECT_NAV_DEFAULT_WIDTH = 300;

function normalizeWidth(value: number): number {
  if (!Number.isFinite(value)) return PROJECT_NAV_DEFAULT_WIDTH;
  return Math.round(Math.min(PROJECT_NAV_MAX_WIDTH, Math.max(PROJECT_NAV_MIN_WIDTH, value)));
}

function storedWidth(): number {
  const value = window.localStorage.getItem(STORAGE_KEY);
  if (value !== null) return normalizeWidth(Number(value));
  const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
  if (legacy === null) return PROJECT_NAV_DEFAULT_WIDTH;
  const numeric = Number(legacy);
  return normalizeWidth(numeric <= 100 ? (window.innerWidth * numeric) / 100 : numeric);
}

export function useProjectNavWidth() {
  const [width, setWidthState] = useState(storedWidth);
  useEffect(() => {
    const sync = () => setWidthState(storedWidth());
    window.addEventListener("storage", sync);
    window.addEventListener(EVENT_NAME, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(EVENT_NAME, sync);
    };
  }, []);
  const setWidth = useCallback((nextWidth: number) => {
    const normalized = normalizeWidth(nextWidth);
    setWidthState(normalized);
    window.localStorage.setItem(STORAGE_KEY, String(normalized));
    window.dispatchEvent(new Event(EVENT_NAME));
  }, []);
  return { width, setWidth };
}
