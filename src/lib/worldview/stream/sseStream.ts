/**
 * Real backend: Server-Sent-Events stream source.
 *
 * Expects an endpoint that streams JSON `WorldviewEvent`s (see ../types.ts).
 * Each SSE message's `data:` payload is one event object; the SSE `event:`
 * field, if present, should mirror the event's `type`. The stream should end
 * with a `done` (or `error`) event.
 *
 * Reconnection: EventSource auto-reconnects on transport drops. We treat a drop
 * before a terminal `done`/`error` as recoverable and surface it; the hook layer
 * decides whether to retry. Cancellation closes the connection cleanly.
 */

import type { WorldviewEvent, WorldviewEventType } from "../types";
import { WORLDVIEW_API_URL } from "./config";
import type { StreamHandle, StreamOptions, StreamSource } from "./source";

/** Every event type, so we can bind a listener per named SSE `event:` field. */
const EVENT_TYPES: WorldviewEventType[] = [
  "query_started",
  "status",
  "district_resolved",
  "cluster_defined",
  "deflection",
  "answer_chunk",
  "research_document",
  "done",
  "error",
];

function buildUrl(query: string, opts: StreamOptions): string {
  const base = WORLDVIEW_API_URL;
  const sep = base.includes("?") ? "&" : "?";
  const params = new URLSearchParams({
    q: query,
    mode: opts.mode ?? "medium",
    provider: opts.provider ?? "azure_anthropic",
  });
  if (opts.deeper) params.set("deeper", "1");
  return `${base}${sep}${params.toString()}`;
}

function parseEvent(raw: string): WorldviewEvent | null {
  try {
    const obj = JSON.parse(raw) as WorldviewEvent;
    return obj && typeof obj === "object" && "type" in obj ? obj : null;
  } catch {
    return null;
  }
}

export const sseStreamSource: StreamSource = (query, opts, handlers) => {
  let closed = false;
  const es = new EventSource(buildUrl(query, opts), { withCredentials: false });

  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
    handlers.onClose();
  };

  const handleMessage = (msg: MessageEvent<string>) => {
    const event = parseEvent(msg.data);
    if (!event) return;
    handlers.onEvent(event);
    if (event.type === "done" || event.type === "error") close();
  };

  // Unnamed frames (no `event:` field) land in onmessage; a backend that mirrors
  // the event type into the SSE `event:` field instead needs a listener per type.
  es.onmessage = handleMessage;
  for (const type of EVENT_TYPES) es.addEventListener(type, handleMessage);

  es.onerror = () => {
    // EventSource fires onerror on transient drops (it will retry) and on fatal
    // failures. If the browser gave up (readyState CLOSED), surface + close.
    if (es.readyState === EventSource.CLOSED) {
      handlers.onError("Connection to the analysis backend was lost.", true);
      close();
    }
  };

  if (opts.signal) {
    if (opts.signal.aborted) close();
    else opts.signal.addEventListener("abort", close, { once: true });
  }

  const handle: StreamHandle = { cancel: close };
  return handle;
};
