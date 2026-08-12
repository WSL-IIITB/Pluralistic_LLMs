/**
 * ── Backend wiring: the ONE place to swap mock ↔ real ────────────────────────
 *
 * Set STREAM_SOURCE to "sse" and point VITE_WORLDVIEW_API_URL at your backend to
 * go live. Leaving it "mock" (the default) runs the fully offline demo.
 *
 * You can also override at runtime without editing this file:
 *   - VITE_WORLDVIEW_STREAM = "mock" | "sse"
 *   - VITE_WORLDVIEW_API_URL = "https://api.example.com/worldview/stream"
 *
 * The real endpoint should accept `?q=<query>&mode=basic|medium|high` (or POST
 * the same) and
 * emit an SSE stream of JSON `WorldviewEvent`s (see ../types.ts), one per
 * `data:` line, ideally with the event `type` mirrored in the SSE `event:` field.
 */

type SourceKind = "mock" | "sse";

const env = (import.meta.env ?? {}) as Record<string, string | undefined>;

/** Change this line (or set VITE_WORLDVIEW_STREAM) to go live. */
const DEFAULT_SOURCE: SourceKind = "mock";

export const STREAM_SOURCE: SourceKind =
  env["VITE_WORLDVIEW_STREAM"] === "sse"
    ? "sse"
    : env["VITE_WORLDVIEW_STREAM"] === "mock"
      ? "mock"
      : DEFAULT_SOURCE;

/** Base URL of the real SSE endpoint (used only when STREAM_SOURCE === "sse"). */
export const WORLDVIEW_API_URL: string = env["VITE_WORLDVIEW_API_URL"] ?? "/api/worldview/stream";

/** Mock playback speed multiplier (1 = authored timing; <1 faster, >1 slower). */
export const MOCK_SPEED: number = (() => {
  const raw = env["VITE_MOCK_SPEED"];
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) && n > 0 ? n : 1;
})();
