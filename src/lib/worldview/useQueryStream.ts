/**
 * useQueryStream — the single hook the UI uses to run a query.
 *
 *   const { run, cancel, retry, isStreaming } = useQueryStream();
 *   run("Diwali");                 // fresh run (resets the view)
 *   run(query, { deeper: true });  // "Go deeper": merges into the current run
 *
 * It opens the active stream source (mock or SSE — chosen in stream/config.ts),
 * feeds every event into the Zustand store, and handles cancellation, unmount
 * cleanup, and a bounded auto-reconnect for recoverable transport errors.
 */

import { useCallback, useEffect, useMemo, useRef } from "react";

import { fetchAllDistrictResearch } from "./districtResearch";
import { saveRun } from "./runHistory";
import {
  createStreamSource,
  type StreamHandle,
  type StreamOptions,
  type StreamSource,
} from "./stream";
import { useWorldviewStore, type RunSnapshot, type RunState } from "./store";
import { escalateMode, type LlmProvider, type ResearchMode } from "./types";

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1500;

export interface RunOptions {
  deeper?: boolean;
  /** Reasoning mode for a fresh run — ignored when `deeper` is true (which escalates the current mode instead). */
  initialMode?: ResearchMode;
  /** LLM provider for a fresh run — ignored when `deeper` is true (which carries forward the current run's provider instead). */
  initialProvider?: LlmProvider;
}

export interface QueryStreamApi {
  run: (query: string, options?: RunOptions) => void;
  cancel: () => void;
  retry: () => void;
  runState: RunState;
  error: string | null;
  isStreaming: boolean;
}

export function useQueryStream(): QueryStreamApi {
  const source = useMemo<StreamSource>(() => createStreamSource(), []);

  const handleRef = useRef<StreamHandle | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);
  const lastRunRef = useRef<{
    query: string;
    deeper: boolean;
    initialMode?: ResearchMode;
    initialProvider?: LlmProvider;
  } | null>(null);
  // Snapshot of accumulated data taken right as this pass started, so a
  // reconnect can rewind to it — a fresh connection restarts server-side
  // collection from zero, and re-delivered district_resolved events would
  // otherwise double-count on top of this pass's already-applied progress.
  const passSnapshotRef = useRef<RunSnapshot | null>(null);

  const runState = useWorldviewStore((s) => s.runState);
  const error = useWorldviewStore((s) => s.error);

  const clearRetry = () => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  };

  const teardown = useCallback(() => {
    clearRetry();
    handleRef.current?.cancel();
    handleRef.current = null;
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const open = useCallback(
    (query: string, options: StreamOptions) => {
      handleRef.current = source(query, options, {
        onEvent: (event) => {
          useWorldviewStore.getState().applyEvent(event);
          // Auto-save every completed run (done OR empty — never error, there's
          // nothing meaningful to redisplay from a failed run) — no explicit
          // "save" step, per the History feature's design.
          if (event.type === "done") {
            const s = useWorldviewStore.getState();
            if ((s.runState === "done" || s.runState === "empty") && s.queryRunId && s.query) {
              const run = {
                id: s.queryRunId,
                query: s.query,
                queryType: s.queryType,
                mode: s.mode,
                provider: s.provider,
                ...s.snapshotRun(),
              };
              // Embed the district research as it stands right now, so reopening this
              // run later shows exactly this research. Falls back to saving without it.
              void fetchAllDistrictResearch().then((districtResearch) =>
                saveRun(districtResearch ? { ...run, districtResearch } : run),
              );
            }
          }
        },
        onError: (message, recoverable) => {
          useWorldviewStore.getState().failRun(message);
          const canRetry =
            recoverable && attemptsRef.current < MAX_RETRIES && !options.signal?.aborted;
          if (canRetry) {
            attemptsRef.current += 1;
            clearRetry();
            retryTimerRef.current = setTimeout(() => {
              if (passSnapshotRef.current) {
                useWorldviewStore.getState().restoreRun(passSnapshotRef.current);
              }
              open(query, options);
            }, RETRY_DELAY_MS);
          }
        },
        onClose: () => {
          handleRef.current = null;
        },
      });
    },
    [source],
  );

  const run = useCallback(
    (query: string, options: RunOptions = {}) => {
      const q = query.trim();
      if (!q) return;
      const deeper = options.deeper ?? false;

      teardown();
      const controller = new AbortController();
      controllerRef.current = controller;
      lastRunRef.current = {
        query: q,
        deeper,
        ...(options.initialMode !== undefined ? { initialMode: options.initialMode } : {}),
        ...(options.initialProvider !== undefined
          ? { initialProvider: options.initialProvider }
          : {}),
      };
      attemptsRef.current = 0;

      const store = useWorldviewStore.getState();
      store.prepareRun({ query: q, deeper });
      passSnapshotRef.current = store.snapshotRun();
      const mode = deeper ? escalateMode(store.mode) : (options.initialMode ?? "medium");
      // "Go deeper" carries forward whichever provider ran the current pass
      // rather than resetting it -- mirrors mode's escalate-in-place semantics.
      const provider = deeper ? store.provider : (options.initialProvider ?? "gemma_remote");

      const streamOpts: StreamOptions = { deeper, mode, provider, signal: controller.signal };
      if (deeper) streamOpts.priorCounts = store.status.counts;
      open(q, streamOpts);
    },
    [open, teardown],
  );

  const cancel = useCallback(() => {
    teardown();
    useWorldviewStore.getState().stop();
  }, [teardown]);

  const retry = useCallback(() => {
    const last = lastRunRef.current;
    if (!last) return;
    run(last.query, {
      deeper: last.deeper,
      ...(last.initialMode !== undefined ? { initialMode: last.initialMode } : {}),
      ...(last.initialProvider !== undefined ? { initialProvider: last.initialProvider } : {}),
    });
  }, [run]);

  // Cancel any in-flight stream on unmount.
  useEffect(() => teardown, [teardown]);

  return {
    run,
    cancel,
    retry,
    runState,
    error,
    isStreaming: runState === "streaming" || runState === "connecting",
  };
}
