/**
 * Offline mock stream — a timed replay of a realistic run so the entire UI is
 * demoable with no backend. Interface-identical to the real SSE source; swap in
 * ./config.ts.
 *
 * Timeline (≈23s at MOCK_SPEED=1): clusters define early → hundreds of real
 * districts resolve and light up the map → points of deflection extract →
 * the consolidated answer streams in token-by-token → done. Geographic
 * coverage is always full (mirrors the real backend); "mode" (basic/medium/
 * high) instead scales how many posts get shown per district and how long
 * the run takes. "Go deeper" escalates the mode and merges in the extra
 * volume by refining confidence on already-seen districts, since there's no
 * new geography left to add.
 */

import {
  type CollectionCounts,
  type LlmProvider,
  type QueryType,
  type ResearchMode,
  type RunPhase,
  type WorldviewEvent,
} from "../types";
import { MOCK_SPEED } from "./config";
import { GENERATED_DISTRICTS, type DistrictSpec } from "./generatedDistricts";
import {
  DIWALI_ANSWER,
  DIWALI_CLUSTERS,
  DIWALI_DEFLECTIONS,
  POLICY_ANSWER,
  POLICY_CLUSTERS,
  POLICY_CLUSTER_REMAP,
  POLICY_DEFLECTIONS,
  type ClusterSpec,
  type DeflectionSpec,
} from "./mockContent";
import { newRunId, type StreamHandle, type StreamSource } from "./source";
import type { AnswerSegment } from "../types";

/** A WorldviewEvent with `queryRunId` omitted, distributed over the union. */
type EventDraft = WorldviewEvent extends infer T
  ? T extends WorldviewEvent
    ? Omit<T, "queryRunId">
    : never
  : never;

const POLICY_RE =
  /\b(should|policy|intervene|intervention|government|govt|recommend|dropout|drop-out|budget|allocate|where to|invest)\b|\?/i;

function detectPolicy(query: string): boolean {
  return POLICY_RE.test(query);
}

interface RunContent {
  queryType: QueryType;
  clusters: ClusterSpec[];
  deflections: DeflectionSpec[];
  answer: AnswerSegment[];
  remap?: Record<string, string>;
}

function contentFor(query: string): RunContent {
  if (detectPolicy(query)) {
    return {
      queryType: "policy",
      clusters: POLICY_CLUSTERS,
      deflections: POLICY_DEFLECTIONS,
      answer: POLICY_ANSWER,
      remap: POLICY_CLUSTER_REMAP,
    };
  }
  return {
    queryType: "descriptive",
    clusters: DIWALI_CLUSTERS,
    deflections: DIWALI_DEFLECTIONS,
    answer: DIWALI_ANSWER,
  };
}

// How much of each district's post volume a mode shows — geography itself
// never shrinks (mirrors the real backend always surveying every state); mode
// only scales the AMOUNT of source volume per district and (below) how long
// the run takes to look for it. "extrahigh" reuses "high"'s factors here --
// the mock has no synthetic per-state cluster/deflection content (a real
// backend-only feature for now), so it plays back identically to "high"
// rather than fully modeling extrahigh's per-state clustering.
const MODE_VOLUME_FACTOR: Record<ResearchMode, number> = {
  basic: 0.45,
  medium: 0.7,
  high: 1,
  extrahigh: 1,
};
const MODE_DURATION_FACTOR: Record<ResearchMode, number> = {
  basic: 0.7,
  medium: 1,
  high: 1.4,
  extrahigh: 1.4,
};

/**
 * Which districts a given pass emits: fresh ones + confidence refinements.
 * Coverage is always the full generated district set — a fresh run always
 * takes the "fresh" branch over ALL districts (just at a mode-scaled volume);
 * "Go deeper" escalates the mode and re-researches, so it has no new
 * geography to add and instead refines confidence on everything already seen.
 */
function districtsForMode(deeper: boolean): { fresh: DistrictSpec[]; refine: DistrictSpec[] } {
  const all = GENERATED_DISTRICTS;
  if (!deeper) return { fresh: all, refine: [] };
  return { fresh: [], refine: all };
}

const bumpConfidence = (c: DistrictSpec["cf"]): DistrictSpec["cf"] =>
  c === "low" ? "medium" : "high";

function statusTicker(phase: RunPhase, counts: CollectionCounts, deeper: boolean): string {
  const posts = counts.postsCollected.toLocaleString("en-IN");
  switch (phase) {
    case "sourcing":
      return deeper
        ? `Extending sampling budget… ${posts} posts and counting`
        : `Sourcing posts across Reddit & YouTube… ${posts} collected`;
    case "researching":
      return `Researching the topic across the open web… ${counts.sourcesGathered} sources gathered`;
    case "resolving":
      return `Resolving posts to districts… ${counts.districtsResolved} districts · ${posts} posts`;
    case "clustering":
      return `Clustering viewpoints… ${counts.clustersFound} clusters across ${counts.districtsResolved} districts`;
    case "deflecting":
      return `Analyzing deflections… ${counts.deflectionsFound} points of deflection found`;
    case "synthesizing":
      return `Synthesizing the consolidated answer…`;
    case "complete":
      return `Done · ${posts} posts · ${counts.districtsResolved} districts · ${counts.clustersFound} clusters · ${counts.deflectionsFound} deflections`;
  }
}

function phaseForFraction(frac: number): RunPhase {
  if (frac < 0.11) return "sourcing";
  if (frac < 0.52) return "resolving";
  if (frac < 0.65) return "clustering";
  if (frac < 0.73) return "deflecting";
  if (frac < 0.995) return "synthesizing";
  return "complete";
}

const DURATION = 23000; // ms at MOCK_SPEED=1, fresh run
const DEEPER_DURATION = 12000; // ms at MOCK_SPEED=1 — the deeper pass's content wraps by ~11.2s

export const mockStreamSource: StreamSource = (query, opts, handlers) => {
  const state = { aborted: false };
  const timers: ReturnType<typeof setTimeout>[] = [];
  const runId = newRunId();
  const mode: ResearchMode = opts.mode ?? "medium";
  const provider: LlmProvider = opts.provider ?? "gemma_remote";
  const deeper = opts.deeper ?? false;
  const durationFactor = MODE_DURATION_FACTOR[mode];
  const volumeFactor = MODE_VOLUME_FACTOR[mode];
  const duration = (deeper ? DEEPER_DURATION : DURATION) * durationFactor;
  const content = contentFor(query);
  const remap = (id: string): string => content.remap?.[id] ?? id;

  const counts: CollectionCounts = {
    postsCollected: opts.priorCounts?.postsCollected ?? 0,
    districtsResolved: opts.priorCounts?.districtsResolved ?? 0,
    clustersFound: opts.priorCounts?.clustersFound ?? (deeper ? content.clusters.length : 0),
    deflectionsFound: opts.priorCounts?.deflectionsFound ?? 0,
    sourcesGathered: opts.priorCounts?.sourcesGathered ?? 0,
    regionsFound: opts.priorCounts?.regionsFound ?? 0,
  };

  const emit = (draft: EventDraft) => {
    if (!state.aborted) handlers.onEvent({ ...draft, queryRunId: runId } as WorldviewEvent);
  };
  const at = (ms: number, fn: () => void) => {
    timers.push(setTimeout(() => !state.aborted && fn(), Math.max(0, ms * MOCK_SPEED)));
  };

  // ── query_started ───────────────────────────────────────────────────────────
  at(0, () =>
    emit({ type: "query_started", query, queryType: content.queryType, mode, provider, t: 0 }),
  );

  // ── periodic status ─────────────────────────────────────────────────────────
  for (let t = 120; t <= duration; t += 650) {
    at(t, () => {
      const frac = t / duration;
      const phase = phaseForFraction(frac);
      const progress = deeper ? 0.6 + 0.4 * frac : frac;
      emit({
        type: "status",
        phase,
        counts: { ...counts },
        progress: Math.min(0.99, progress),
        ticker: statusTicker(phase, counts, deeper),
        t,
      });
    });
  }

  // ── cluster_defined (early, so columns colour correctly) ─────────────────────
  if (!deeper) {
    content.clusters.forEach((c, i) => {
      at(800 + i * 260, () => {
        counts.clustersFound = Math.max(counts.clustersFound, i + 1);
        emit({
          type: "cluster_defined",
          clusterId: c.id,
          label: c.label,
          color: c.color,
          summary: c.summary,
          representativePosts: c.posts,
        });
      });
    });
  }

  // ── district_resolved (fresh + refinements) ──────────────────────────────────
  const { fresh, refine } = districtsForMode(deeper);
  const D_START = (deeper ? 400 : 2500) * durationFactor;
  const D_END = (deeper ? 9000 : 15000) * durationFactor;
  const BATCH = 6;
  const emitDistrict = (spec: DistrictSpec, refined: boolean) => {
    const cf = refined ? bumpConfidence(spec.cf) : spec.cf;
    const volume = Math.max(1, Math.round(spec.v * (refined ? 0.6 : 1) * volumeFactor));
    counts.postsCollected += volume;
    counts.districtsResolved += refined ? 0 : 1;
    emit({
      type: "district_resolved",
      districtId: spec.d,
      stateCode: spec.s,
      clusterId: remap(spec.c),
      confidence: cf,
      volume,
      method: spec.m,
      isStateFallback: refined ? false : spec.f === 1,
    });
  };

  const queue: Array<{ spec: DistrictSpec; refined: boolean }> = [
    ...fresh.map((spec) => ({ spec, refined: false })),
    ...refine.map((spec) => ({ spec, refined: true })),
  ];
  const total = Math.max(1, queue.length);
  for (let i = 0; i < queue.length; i += BATCH) {
    const chunk = queue.slice(i, i + BATCH);
    const t = D_START + (D_END - D_START) * (i / total);
    at(t, () => chunk.forEach(({ spec, refined }) => emitDistrict(spec, refined)));
  }

  // ── deflection ────────────────────────────────────────────────────────────────
  content.deflections.forEach((d, i) => {
    at((deeper ? 9200 : 15200) * durationFactor + i * 300, () => {
      counts.deflectionsFound = Math.max(counts.deflectionsFound, i + 1);
      emit({
        type: "deflection",
        id: d.id,
        clusterA: d.clusterA,
        clusterB: d.clusterB,
        level: d.level,
        unitA: d.unitA,
        unitB: d.unitB,
        point: d.point,
        confidence: deeper && d.confidence === "low" ? "medium" : d.confidence,
      });
    });
  });

  // ── answer_chunk (streamed token-by-token) ────────────────────────────────────
  const answerStart = (deeper ? 11000 : 16800) * durationFactor;
  if (deeper) {
    // Don't re-stream the whole answer; append a short refinement note.
    at(answerStart, () =>
      emit({
        type: "answer_chunk",
        segment: {
          kind: "body",
          text: `\n\nDeeper pass complete: research widened to ${mode} mode and confidence was refined across all ${counts.districtsResolved} districts. The regional split held.`,
        },
      }),
    );
  } else {
    let cursor = answerStart;
    for (const seg of content.answer) {
      if (seg.kind === "heading" || seg.kind === "recommendation") {
        const headSeg = seg;
        at(cursor, () => emit({ type: "answer_chunk", segment: headSeg }));
        cursor += seg.kind === "heading" ? 260 : 200;
      } else {
        // Stream body text in ~3-word groups for a typing effect.
        const leadingBreak = /^\s*\n\s*\n/.test(seg.text);
        const words = seg.text.replace(/^\s*\n\s*\n/, "").split(/(\s+)/);
        let acc = "";
        let count = 0;
        let first = true;
        const flush = () => {
          const chunk = acc;
          const prefix = first && leadingBreak ? "\n\n" : "";
          const base: AnswerSegment = { kind: "body", text: prefix + chunk };
          const segment: AnswerSegment = seg.clusterId
            ? { ...base, clusterId: seg.clusterId }
            : base;
          at(cursor, () => emit({ type: "answer_chunk", segment }));
          cursor += 95;
          acc = "";
          count = 0;
          first = false;
        };
        for (const w of words) {
          acc += w;
          if (w.trim().length > 0) count += 1;
          if (count >= 3) flush();
        }
        if (acc.length > 0) flush();
      }
    }
  }

  // ── done ──────────────────────────────────────────────────────────────────────
  at(duration, () => {
    const phase: RunPhase = "complete";
    emit({
      type: "status",
      phase,
      counts: { ...counts },
      progress: 1,
      ticker: statusTicker(phase, counts, deeper),
      t: duration,
    });
    emit({ type: "done", counts: { ...counts }, t: duration });
    finish();
  });

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    handlers.onClose();
  };

  const cancel = () => {
    if (state.aborted) return;
    state.aborted = true;
    for (const timer of timers) clearTimeout(timer);
    finish();
  };

  if (opts.signal) {
    if (opts.signal.aborted) cancel();
    else opts.signal.addEventListener("abort", cancel, { once: true });
  }

  const handle: StreamHandle = { cancel };
  return handle;
};
