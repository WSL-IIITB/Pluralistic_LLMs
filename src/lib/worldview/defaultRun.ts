/**
 * The dashboard opens on a finished analysis instead of an empty query box: the
 * newest saved run that has both Story-vs-UIDAI/NITI and persona-similarity
 * results is loaded on start-up. Falls back silently to an empty dashboard.
 */

import { assetUrl, STATIC_DATA } from "./api";
import { fetchSavedRun, listSavedRuns } from "./runHistory";
import { useWorldviewStore } from "./store";

const MAX_RUNS_TO_TRY = 12;

export async function loadDefaultRun(): Promise<boolean> {
  const store = useWorldviewStore.getState();
  if (store.runState !== "idle" || store.queryRunId) return false;
  if (STATIC_DATA) {
    // Static build: the chosen run was exported to public/data/default-run.json.
    try {
      const res = await fetch(assetUrl("data/default-run.json"));
      if (!res.ok) return false;
      const data = (await res.json()) as Parameters<typeof store.loadSavedRun>[0];
      if (useWorldviewStore.getState().queryRunId) return false;
      useWorldviewStore.getState().loadSavedRun(data);
      return true;
    } catch {
      return false;
    }
  }
  const runs = await listSavedRuns(); // newest first
  for (const summary of runs.slice(0, MAX_RUNS_TO_TRY)) {
    const data = await fetchSavedRun(summary.id);
    if (!data) continue;
    const hasStory = Object.keys(data.storyVsOfficial ?? {}).length > 0;
    const hasSimilarity = Object.keys(data.personaSimilarity ?? {}).length > 0;
    if (hasStory && hasSimilarity) {
      // The user may have opened something else while this was loading.
      if (useWorldviewStore.getState().queryRunId) return false;
      useWorldviewStore.getState().loadSavedRun(data);
      return true;
    }
  }
  return false;
}
