import { useCallback, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
const KEY = "fstack-starter:theme";
const EVENT = "app:theme";

function current(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0e0e10" : "#fafafa");
}

/** Cross-fade the whole UI when the browser supports view transitions. */
export function withTransition(change: () => void) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce && "startViewTransition" in document) {
    (document as Document & { startViewTransition: (cb: () => void) => unknown }).startViewTransition(change);
  } else {
    change();
  }
}

export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore((onChange) => {
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, current);
  const toggle = useCallback(() => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    // A view transition runs its callback later: announce the change once it's applied.
    withTransition(() => {
      applyTheme(next);
      window.dispatchEvent(new Event(EVENT));
    });
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode */
    }
  }, []);
  return [theme, toggle];
}
