/**
 * Data View's Server-Sent-Events stream source.
 *
 * Mirrors `src/lib/worldview/stream/sseStream.ts`'s EventSource wiring exactly
 * (same connection/reconnection/error-handling shape, same EVENT_TYPES-driven
 * addEventListener loop) but simplified: Data View is a single, parameterless
 * bootstrap load (no query/mode/provider), so there's no `buildUrl` — just the
 * one fixed endpoint from ./config.
 *
 * Reconnection: EventSource auto-reconnects on transport drops. We treat a drop
 * before a terminal `done`/`error` as recoverable and surface it; the hook/
 * store layer decides whether to retry. Cancellation closes the connection
 * cleanly.
 */

import type { DataViewEvent, DataViewEventType } from "../types";
import { DATAVIEW_API_URL } from "./config";

/** Every event type, so we can bind a listener per named SSE `event:` field. */
const EVENT_TYPES: DataViewEventType[] = [
  "factor_defined",
  "district_scored",
  "state_scored",
  "done",
  "error",
];

export interface DataViewStreamHandlers {
  onEvent: (event: DataViewEvent) => void;
  /** Transport/terminal error. `recoverable` hints whether a retry may help. */
  onError: (message: string, recoverable: boolean) => void;
  /** Fired exactly once when the stream closes (done, error, or cancel). */
  onClose: () => void;
}

export interface DataViewStreamHandle {
  cancel: () => void;
}

function parseEvent(raw: string): DataViewEvent | null {
  try {
    const obj = JSON.parse(raw) as DataViewEvent;
    return obj && typeof obj === "object" && "type" in obj ? obj : null;
  } catch {
    return null;
  }
}

/** Open the Data View bootstrap stream. Takes no query params — see module doc comment. */
export function openDataViewStream(handlers: DataViewStreamHandlers): DataViewStreamHandle {
  let closed = false;
  const es = new EventSource(DATAVIEW_API_URL, { withCredentials: false });

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
      handlers.onError("Connection to the Data View backend was lost.", true);
      close();
    }
  };

  return { cancel: close };
}
