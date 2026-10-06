/**
 * Stream-source factory. Reads STREAM_SOURCE (config.ts) and returns the active
 * implementation. This is the seam the app depends on; swapping mock↔real is a
 * one-line change in config.ts.
 */

import { STREAM_SOURCE } from "./config";
import { mockStreamSource } from "./mockStream";
import { sseStreamSource } from "./sseStream";
import type { StreamSource } from "./source";

export function createStreamSource(): StreamSource {
  return STREAM_SOURCE === "sse" ? sseStreamSource : mockStreamSource;
}

export { STREAM_SOURCE } from "./config";
export type { StreamHandlers, StreamHandle, StreamOptions, StreamSource } from "./source";
