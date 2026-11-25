/**
 * The dashboard opens on a finished analysis instead of an empty query box: the newest saved run for the active
 * study topic (dropout: Story-vs-UIDAI/NITI and persona-similarity results; stunting: a run on a stunting question)
 * is loaded on start-up and whenever the topic is switched. Falls back silently.
 */

import { assetUrl, STATIC_DATA } from "./api";
import { fetchSavedRun, listSavedRuns } from "./runHistory";
import { useWorldviewStore } from "./store";
import type { StudyTopic } from "./stunting";

const MAX_RUNS_TO_TRY = 12;

/** Mirrors backend/app/stunting.py is_stunting_query: which study a run's question belongs to. */
export function runTopic(query: string | null | undefined): StudyTopic {
  return /stunt|malnutri|malnourish|undernutri|undernourish|child nutrition/i.test(query ?? "")
    ? "stunting"
    : "dropout";
}

export async function loadDefaultRun(
  topic: StudyTopic = "dropout",
  force = false,
): Promise<boolean> {
  const store = useWorldviewStore.getState();
  if (store.runState === "connecting" || store.runState === "streaming") return false;
  if (!force && (store.runState !== "idle" || store.queryRunId)) return false;
  if (force && store.queryRunId && runTopic(store.query) === topic) return false; // already showing this topic
  const startedOn = store.queryRunId;
  const stillFree = () => useWorldviewStore.getState().queryRunId === startedOn;
  if (STATIC_DATA) {
    // Static build: each topic's chosen run was exported to public/data/.
    try {
      const res = await fetch(
        assetUrl(topic === "stunting" ? "data/default-run-stunting.json" : "data/default-run.json"),
      );
      if (!res.ok) return false;
      const data = (await res.json()) as Parameters<typeof store.loadSavedRun>[0];
      if (!stillFree()) return false;
      useWorldviewStore.getState().loadSavedRun(data);
      return true;
    } catch {
      return false;
    }
  }
  const runs = await listSavedRuns(); // newest first
  for (const summary of runs.filter((r) => runTopic(r.query) === topic).slice(0, MAX_RUNS_TO_TRY)) {
    const data = await fetchSavedRun(summary.id);
    if (!data) continue;
    const hasStory = Object.keys(data.storyVsOfficial ?? {}).length > 0;
    const hasSimilarity = Object.keys(data.personaSimilarity ?? {}).length > 0;
    if (hasStory && (hasSimilarity || topic === "stunting")) {
      // The user may have opened something else while this was loading.
      if (!stillFree()) return false;
      useWorldviewStore.getState().loadSavedRun(data);
      return true;
    }
  }
  return false;
}
