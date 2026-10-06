/**
 * Offline demo stream — a timed replay of a REAL captured Karnataka run
 * (./demoRun.json: every event the backend emitted, queryRunId stripped), so
 * the whole UI, divergence view included, is demoable with no backend. It
 * always replays that one run, whatever the query. Interface-identical to the
 * SSE source; swap in ./config.ts.
 *
 * Regenerate demoRun.json from a saved SSE capture with
 * `node scripts/build-demo-run.mjs <capture.sse>`.
 */

import type { WorldviewEvent } from "../types";
import { MOCK_SPEED } from "./config";
import demoRun from "./demoRun.json";
import { newRunId, type StreamHandle, type StreamSource } from "./source";

type EventDraft = WorldviewEvent extends infer T
  ? T extends WorldviewEvent
    ? Omit<T, "queryRunId">
    : never
  : never;

const EVENTS = demoRun.events as unknown as EventDraft[];
export const DEMO_QUERY: string = demoRun.query;
/** Whole replay length at MOCK_SPEED = 1. */
const DURATION_MS = 24_000;

export const mockStreamSource: StreamSource = (_query, opts, handlers) => {
  const runId = newRunId();
  const step = (DURATION_MS * MOCK_SPEED) / Math.max(1, EVENTS.length);
  let i = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    if (timer) clearTimeout(timer);
    handlers.onClose();
  };

  const tick = () => {
    if (closed) return;
    const draft = EVENTS[i++];
    if (!draft) return close();
    const event = { ...draft, queryRunId: runId } as WorldviewEvent;
    if (event.type === "query_started" && opts.mode) event.mode = opts.mode;
    handlers.onEvent(event);
    if (event.type === "done" || event.type === "error") return close();
    timer = setTimeout(tick, step);
  };

  if (opts.signal?.aborted) close();
  else {
    opts.signal?.addEventListener("abort", close, { once: true });
    timer = setTimeout(tick, 150);
  }
  const handle: StreamHandle = { cancel: close };
  return handle;
};
