/**
 * ── Backend wiring for Data View ─────────────────────────────────────────────
 *
 * Unlike Worldview, Data View has no mock/offline mode: it's a single,
 * parameterless bootstrap load of real government data (UDISE+/NFHS-5,
 * pre-modeled server-side), not a per-query demo. `VITE_DATAVIEW_STREAM`
 * exists only for shape-parity with `worldview/stream/config.ts` and today
 * has exactly one supported value.
 *
 * Override at runtime without editing this file:
 *   - VITE_DATAVIEW_STREAM  = "sse" (default, only supported value)
 *   - VITE_DATAVIEW_API_URL = "http://localhost:8001/api/dataview/stream"
 *
 * The real endpoint takes no query params and emits an SSE stream of JSON
 * `DataViewEvent`s (see ../types.ts), one per `data:` line, ideally with the
 * event `type` mirrored in the SSE `event:` field, ending in `done`.
 */

type DataViewSourceKind = "sse";

const env = (import.meta.env ?? {}) as Record<string, string | undefined>;

/** Only supported value today — kept as a named constant for parity with worldview/stream/config.ts. */
const DEFAULT_SOURCE: DataViewSourceKind = "sse";

export const DATAVIEW_STREAM_SOURCE: DataViewSourceKind =
  env["VITE_DATAVIEW_STREAM"] === "sse" ? "sse" : DEFAULT_SOURCE;

/** Base URL of the SSE bootstrap endpoint. */
export const DATAVIEW_API_URL: string =
  env["VITE_DATAVIEW_API_URL"] ?? "http://localhost:8001/api/dataview/stream";
