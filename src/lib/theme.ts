/**
 * Light/dark theme. Light is the default; "dark" is the `.dark` class on <html>
 * (see styles.css). The choice is remembered in localStorage and applied by an
 * inline script in __root.tsx before first paint, so there is no flash.
 */

import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

export const THEME_KEY = "wv.theme";

/** Runs in <head> before paint. Keep in sync with setTheme below. */
export const THEME_INIT_SCRIPT = `try{if(localStorage.getItem("${THEME_KEY}")==="dark")document.documentElement.classList.add("dark")}catch(e){}`;

const listeners = new Set<() => void>();

export function getTheme(): Theme {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark")
    ? "dark"
    : "light";
}

export function setTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // private mode / blocked storage: the choice just won't persist
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getTheme, () => "light");
}
