/**
 * Where the frontend gets its data.
 *
 * Normally everything comes from the analysis backend (see apiUrl). The GitHub Pages
 * build has no backend: `VITE_STATIC_DATA=1` makes the same calls read JSON snapshots
 * that scripts/export_static_data.py wrote into public/data/ -- so the dashboard shows
 * the finished study but can't run new queries or save runs.
 */

import { WORLDVIEW_API_URL } from "./stream/config";

export const STATIC_DATA: boolean =
  ((import.meta.env ?? {}) as Record<string, string | undefined>)["VITE_STATIC_DATA"] === "1";

/** A file under public/, correct whether the site is served from "/" or from a sub-path (GitHub Pages). */
export function assetUrl(path: string): string {
  const base = ((import.meta.env ?? {}) as Record<string, string | undefined>)["BASE_URL"] ?? "/";
  return `${base.endsWith("/") ? base : `${base}/`}${path.replace(/^\//, "")}`;
}

export function apiUrl(path: string): string {
  try {
    const origin = new URL(WORLDVIEW_API_URL, window.location.origin).origin;
    return `${origin}${path}`;
  } catch {
    return path;
  }
}

/** API path -> the static snapshot that stands in for it. */
const STATIC_FILES: Record<string, string> = {
  "/api/karnataka/districts": "data/districts.json",
  "/api/personas": "data/personas.json",
  "/api/karnataka/districts-research": "data/districts-research.json",
};

/** URL to read an API resource from: the backend, or its snapshot in a static build. */
export function dataUrl(path: string): string {
  if (!STATIC_DATA) return apiUrl(path);
  const file = STATIC_FILES[path];
  return file ? assetUrl(file) : path;
}

/** Fetch-once JSON loader with a module-level cache; resolves null on failure. */
export function cachedJson<T>(path: string): () => Promise<T | null> {
  let inflight: Promise<T | null> | null = null;
  return () => {
    inflight ??= fetch(dataUrl(path))
      .then((r) => (r.ok ? (r.json() as Promise<T>) : null))
      .catch(() => null);
    return inflight;
  };
}
