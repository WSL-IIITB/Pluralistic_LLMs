/**
 * Stream-source abstraction.
 *
 * A `StreamSource` opens a run for a query and pushes typed {@link WorldviewEvent}s
 * to the caller until the run ends or is cancelled. Two implementations ship:
 *
 *   • mockStreamSource — a timed, offline replay (Diwali / policy). Default.
 *   • sseStreamSource  — a real Server-Sent-Events backend.
 *
 * Swapping them is a one-line change in ./config.ts (STREAM_SOURCE).
 */

import type { CollectionCounts, LlmProvider, ResearchMode, WorldviewEvent } from "../types";

export interface StreamHandlers {
  onEvent: (event: WorldviewEvent) => void;
  /** Transport/terminal error. `recoverable` hints whether a retry may help. */
  onError: (message: string, recoverable: boolean) => void;
  /** Fired exactly once when the stream closes (done, error, or cancel). */
  onClose: () => void;
}

export interface StreamOptions {
  /** True when refining an existing run ("Go deeper") rather than starting fresh. */
  deeper?: boolean;
  /** Basic/medium/high — see {@link ResearchMode}. Escalated on "Go deeper". */
  mode?: ResearchMode;
  /** Which LLM backend answers this run — see {@link LlmProvider}. Carried forward on "Go deeper". */
  provider?: LlmProvider;
  /** Prior cumulative counts, so a "Go deeper" ticker stays monotonic (mock only). */
  priorCounts?: CollectionCounts;
  /** External cancellation. */
  signal?: AbortSignal;
}

export interface StreamHandle {
  cancel: () => void;
}

export type StreamSource = (
  query: string,
  options: StreamOptions,
  handlers: StreamHandlers,
) => StreamHandle;

/** Generate a run id (crypto.randomUUID when available, else a timestamp id). */
export function newRunId(): string {
  const c = typeof globalThis !== "undefined" ? globalThis.crypto : undefined;
  if (c && typeof c.randomUUID === "function") return `run_${c.randomUUID()}`;
  return `run_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e6).toString(36)}`;
}
