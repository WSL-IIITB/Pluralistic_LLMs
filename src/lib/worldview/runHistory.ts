/**
 * Saved-run history: thin fetch wrapper around the backend's
 * `/api/worldview/runs` endpoints (see backend/app/run_history.py). Mirrors
 * the `stream/` module's separation of concerns — this file owns the network
 * calls, the store owns the state, components own the UI.
 *
 * Every function here fails soft: a saved-run fetch/save/delete going wrong
 * should never break the live dashboard. Callers can treat the return values
 * (empty array / null / false) as the only signal they need; errors are
 * logged, never thrown.
 */

import { STATIC_DATA } from "./api";
import { STREAM_SOURCE, WORLDVIEW_API_URL } from "./stream/config";
import type { SavedRunData } from "./store";
import type { SavedRunSummary } from "./types";

/** Same origin as the SSE stream endpoint, swapping the path's tail. */
const RUNS_URL = WORLDVIEW_API_URL.replace(/\/stream$/, "/runs");

/** No real backend to persist to in the offline mock demo — every function
 * below short-circuits on this rather than attempting (and failing) a fetch. */
const hasBackend = STREAM_SOURCE === "sse" && !STATIC_DATA;

/** Fire-and-forget: save a completed run. Never throws. */
export async function saveRun(data: SavedRunData): Promise<void> {
  if (!hasBackend) return;
  try {
    const res = await fetch(RUNS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) console.warn("Failed to save run history:", res.status);
  } catch (err) {
    console.warn("Failed to save run history:", err);
  }
}

/** All saved runs, newest first. Empty array on any failure. */
export async function listSavedRuns(): Promise<SavedRunSummary[]> {
  if (!hasBackend) return [];
  try {
    const res = await fetch(RUNS_URL);
    if (!res.ok) return [];
    return (await res.json()) as SavedRunSummary[];
  } catch (err) {
    console.warn("Failed to load run history:", err);
    return [];
  }
}

/** The full data for one saved run, or null if it doesn't exist / on failure. */
export async function fetchSavedRun(id: string): Promise<SavedRunData | null> {
  if (!hasBackend) return null;
  try {
    const res = await fetch(`${RUNS_URL}/${encodeURIComponent(id)}`);
    if (!res.ok) return null;
    return (await res.json()) as SavedRunData;
  } catch (err) {
    console.warn("Failed to load saved run:", err);
    return null;
  }
}

/** True if the run was deleted. False on 404 or any failure. */
export async function deleteSavedRun(id: string): Promise<boolean> {
  if (!hasBackend) return false;
  try {
    const res = await fetch(`${RUNS_URL}/${encodeURIComponent(id)}`, { method: "DELETE" });
    return res.ok;
  } catch (err) {
    console.warn("Failed to delete saved run:", err);
    return false;
  }
}
