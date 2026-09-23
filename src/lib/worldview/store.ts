/**
 * Worldview run store (Zustand).
 *
 * Holds everything derived from one query run — posts→Karnataka regions, clusters,
 * deflections, the consolidated answer, and progress — keyed by `queryRunId`.
 *
 * The store is designed so a re-run ("Go deeper") MERGES into the existing
 * state rather than replacing it: call `prepareRun({ deeper: true })` and the
 * accumulated regions/clusters/answer are kept while new events refine them.
 */

import { create } from "zustand";

import {
  type AnswerSegment,
  type ClusterDatum,
  type ClusterId,
  type CollectionCounts,
  type DeflectionDatum,
  type DivergenceModels,
  type DivergenceRegion,
  type DivergenceSummary,
  type LlmProvider,
  type QueryRunId,
  type QueryType,
  type RegionDatum,
  type RegionId,
  type RegionStatsDatum,
  type ResearchDocument,
  type ResearchMode,
  type RunPhase,
  type WorldviewEvent,
} from "./types";
import { regionColor } from "./karnataka";
import { paletteColor, paletteColorForRegionHue } from "./palette";

export type RunState = "idle" | "connecting" | "streaming" | "done" | "error" | "empty";

export interface StatusSnapshot {
  ticker: string;
  phase: RunPhase;
  counts: CollectionCounts;
  /** 0–1 collection progress. */
  progress: number;
}

export interface LayerToggles {
  columns: boolean;
  links: boolean;
  /** Outline regions whose viewpoints are genuinely split (see splitRegionIds). */
  splitRegions: boolean;
}

export type Selection = { kind: "region"; id: RegionId } | { kind: null; id: null };

/** Accumulated-data slice, captured before a pass starts so a reconnect can rewind to it. */
export interface RunSnapshot {
  /** Per Karnataka region (plus the statewide bucket). */
  regionStats: Record<RegionId, RegionStatsDatum>;
  clusters: Record<ClusterId, ClusterDatum>;
  clusterOrder: ClusterId[];
  regions: Record<RegionId, RegionDatum>;
  regionOrder: RegionId[];
  deflections: DeflectionDatum[];
  answer: AnswerSegment[];
  researchDocuments: ResearchDocument[];
  /** Persona vs. no-persona divergence, per model then per region, as each is measured. */
  divergence: Partial<Record<LlmProvider, Record<RegionId, DivergenceRegion>>>;
  divergenceSummary: Partial<Record<LlmProvider, DivergenceSummary>>;
  divergenceModels: DivergenceModels | null;
  status: StatusSnapshot;
}

/**
 * Everything needed to redisplay a completed run later, exactly as it looked
 * when the run finished — the same accumulated-data slice `RunSnapshot`
 * already captures, plus the run's identity fields (which `RunSnapshot`
 * deliberately omits, since reconnect-rewind never changes them). Defined
 * here rather than in types.ts to avoid types.ts importing back from this
 * file. POSTed verbatim to the backend on completion (see runHistory.ts) and
 * fetched back verbatim to reopen — the backend never inspects this shape.
 */
export interface SavedRunData extends RunSnapshot {
  id: QueryRunId;
  query: string;
  queryType: QueryType;
  mode: ResearchMode;
  provider: LlmProvider;
}

const EMPTY_COUNTS: CollectionCounts = {
  postsCollected: 0,
  districtsResolved: 0,
  clustersFound: 0,
  deflectionsFound: 0,
  sourcesGathered: 0,
  regionsFound: 0,
};

const IDLE_STATUS: StatusSnapshot = {
  ticker: "Enter a topic to begin — the map builds live as posts are sourced and resolved.",
  phase: "sourcing",
  counts: EMPTY_COUNTS,
  progress: 0,
};

export interface WorldviewStore {
  // ── run identity ──────────────────────────────────────────────────────────
  queryRunId: QueryRunId | null;
  query: string | null;
  queryType: QueryType;
  mode: ResearchMode;
  provider: LlmProvider;
  runState: RunState;
  error: string | null;
  status: StatusSnapshot;
  /** True when the loaded saved run predates the Karnataka pivot (India-wide, district-level). */
  legacyRun: boolean;

  // ── accumulated data ────────────────────────────────────────────────────────
  regionStats: Record<RegionId, RegionStatsDatum>;
  clusters: Record<ClusterId, ClusterDatum>;
  clusterOrder: ClusterId[];
  regions: Record<RegionId, RegionDatum>;
  regionOrder: RegionId[];
  deflections: DeflectionDatum[];
  answer: AnswerSegment[];
  /** Web-search-grounded sources gathered by the research stage, in id order,
   *  deduped by URL. Rendered as the "Sources" section of the consolidated
   *  answer panel; also referenced from AnswerSegment.citations (1-based ids). */
  researchDocuments: ResearchDocument[];
  divergence: Partial<Record<LlmProvider, Record<RegionId, DivergenceRegion>>>;
  divergenceSummary: Partial<Record<LlmProvider, DivergenceSummary>>;
  divergenceModels: DivergenceModels | null;

  // ── view state ──────────────────────────────────────────────────────────────
  layers: LayerToggles;
  selection: Selection;
  hoveredClusterId: ClusterId | null;
  deflectionPair: { a: ClusterId | null; b: ClusterId | null };

  // ── actions ─────────────────────────────────────────────────────────────────
  prepareRun(input: { query: string; deeper?: boolean }): void;
  applyEvent(evt: WorldviewEvent): void;
  finishRun(result: "done" | "empty"): void;
  failRun(message: string): void;
  /** User-initiated stop: settle into a terminal state without wiping data. */
  stop(): void;
  /** Capture the accumulated-data slice, e.g. right after prepareRun, for reconnect rewind. */
  snapshotRun(): RunSnapshot;
  /** Rewind to a prior snapshot (discarding whatever the failed pass had applied) and reconnect. */
  restoreRun(snapshot: RunSnapshot): void;
  /** Redisplay a previously-saved, already-completed run — unlike `restoreRun`
   *  (reconnect-rewind, mid-stream), this settles into a terminal "done" state. */
  loadSavedRun(data: SavedRunData): void;
  setLayer(key: keyof LayerToggles, value: boolean): void;
  toggleLayer(key: keyof LayerToggles): void;
  select(selection: Selection): void;
  clearSelection(): void;
  setHoveredCluster(id: ClusterId | null): void;
  setDeflectionPair(a: ClusterId | null, b: ClusterId | null): void;
  reset(): void;
}

const NO_SELECTION: Selection = { kind: null, id: null };

/** argmax over a cluster→volume record. */
function dominantCluster(volumes: Record<ClusterId, number>): ClusterId | null {
  let best: ClusterId | null = null;
  let bestVol = -Infinity;
  for (const id of Object.keys(volumes)) {
    const v = volumes[id] ?? 0;
    if (v > bestVol) {
      bestVol = v;
      best = id;
    }
  }
  return best;
}

function countForRegion(
  clusters: Record<ClusterId, ClusterDatum>,
  order: readonly ClusterId[],
  regionId: RegionId,
): number {
  let count = 0;
  for (const id of order) {
    if (clusters[id]?.regionId === regionId) count++;
  }
  return count;
}

/** Ensure a cluster stub exists so events can arrive in any order. A cluster
 * with a region takes that region's fixed identity hue (lightness-stepped per
 * cluster); the backend's own colour is only used for region-less clusters. */
function ensureCluster(
  clusters: Record<ClusterId, ClusterDatum>,
  order: ClusterId[],
  id: ClusterId,
  regionId?: RegionId,
): ClusterDatum {
  const existing = clusters[id];
  if (existing) return existing;
  const color = regionId
    ? paletteColorForRegionHue(regionColor(regionId), countForRegion(clusters, order, regionId))
    : paletteColor(order.length);
  const stub: ClusterDatum = {
    id,
    label: id,
    color,
    ...(regionId ? { regionId } : {}),
    representativePosts: [],
    postCount: 0,
  };
  clusters[id] = stub;
  order.push(id);
  return stub;
}

/** Region-id prefix of a region-scoped cluster id (`"malnad:c0"` -> `"malnad"`). */
function regionIdFromClusterId(id: ClusterId): RegionId | undefined {
  const i = id.indexOf(":");
  return i > 0 ? id.slice(0, i) : undefined;
}

const EMPTY_DATA = {
  regionStats: {},
  clusters: {},
  clusterOrder: [],
  regions: {},
  regionOrder: [],
  deflections: [],
  answer: [],
  researchDocuments: [],
  divergence: {},
  divergenceSummary: {},
  divergenceModels: null,
} satisfies Omit<RunSnapshot, "status">;

export const useWorldviewStore = create<WorldviewStore>((set, get) => ({
  queryRunId: null,
  query: null,
  queryType: "descriptive",
  mode: "medium",
  provider: "gemma_remote",
  runState: "idle",
  error: null,
  status: IDLE_STATUS,
  legacyRun: false,

  ...EMPTY_DATA,

  layers: { columns: true, links: true, splitRegions: true },
  selection: NO_SELECTION,
  hoveredClusterId: null,
  deflectionPair: { a: null, b: null },

  prepareRun: ({ query, deeper = false }) => {
    if (deeper) {
      // Keep accumulated data; just flip into a connecting state.
      set({ query, runState: "connecting", error: null });
      return;
    }
    set({
      query,
      runState: "connecting",
      error: null,
      queryRunId: null,
      mode: "medium",
      provider: "gemma_remote",
      legacyRun: false,
      status: { ...IDLE_STATUS, ticker: `Sourcing posts for “${query}”…`, progress: 0.01 },
      ...EMPTY_DATA,
      selection: NO_SELECTION,
      hoveredClusterId: null,
      deflectionPair: { a: null, b: null },
    });
  },

  applyEvent: (evt) => {
    switch (evt.type) {
      case "query_started": {
        set({
          queryRunId: evt.queryRunId,
          query: evt.query,
          queryType: evt.queryType,
          mode: evt.mode,
          provider: evt.provider,
          runState: "streaming",
          error: null,
        });
        return;
      }

      case "status": {
        set({
          runState: "streaming",
          status: {
            ticker: evt.ticker,
            phase: evt.phase,
            counts: evt.counts,
            progress: Math.max(0, Math.min(1, evt.progress)),
          },
        });
        return;
      }

      case "region_defined": {
        set((s) => {
          if (s.regions[evt.regionId]) return {};
          const region: RegionDatum = {
            id: evt.regionId,
            name: evt.name,
            justification: evt.justification,
            districtIds: evt.districtIds,
            stateCodes: evt.stateCodes,
            confidence: evt.confidence,
          };
          return {
            regions: { ...s.regions, [evt.regionId]: region },
            regionOrder: [...s.regionOrder, evt.regionId],
          };
        });
        return;
      }

      case "cluster_defined": {
        set((s) => {
          const clusters = { ...s.clusters };
          const order = [...s.clusterOrder];
          const regionId = evt.regionId ?? regionIdFromClusterId(evt.clusterId);
          const prev = ensureCluster(clusters, order, evt.clusterId, regionId);
          clusters[evt.clusterId] = {
            ...prev,
            label: evt.label,
            color: prev.regionId ? prev.color : evt.color,
            ...(evt.summary !== undefined ? { summary: evt.summary } : {}),
            representativePosts: evt.representativePosts ?? prev.representativePosts,
          };
          return { clusters, clusterOrder: order };
        });
        return;
      }

      case "region_resolved": {
        set((s) => {
          const clusters = { ...s.clusters };
          const order = [...s.clusterOrder];
          ensureCluster(clusters, order, evt.clusterId, evt.regionId);
          const prev = s.regionStats[evt.regionId];
          const clusterVolumes = { ...(prev?.clusterVolumes ?? {}) };
          clusterVolumes[evt.clusterId] = (clusterVolumes[evt.clusterId] ?? 0) + evt.volume;
          const samplePosts = [...(prev?.samplePosts ?? []), ...(evt.samplePosts ?? [])].slice(
            0,
            8,
          );
          const regionStats = {
            ...s.regionStats,
            [evt.regionId]: {
              regionId: evt.regionId,
              clusterId: dominantCluster(clusterVolumes),
              clusterVolumes,
              volume: (prev?.volume ?? 0) + evt.volume,
              confidence: evt.confidence,
              method: evt.method,
              samplePosts,
            },
          };
          const cl = clusters[evt.clusterId];
          if (cl) clusters[evt.clusterId] = { ...cl, postCount: cl.postCount + evt.volume };
          return { regionStats, clusters, clusterOrder: order };
        });
        return;
      }

      case "divergence_region": {
        const { type: _t, queryRunId: _q, t: _time, ...region } = evt;
        set((s) => ({
          divergence: {
            ...s.divergence,
            [evt.model]: { ...s.divergence[evt.model], [evt.regionId]: region },
          },
        }));
        return;
      }

      case "divergence_summary": {
        const { type: _t, queryRunId: _q, t: _time, ...summary } = evt;
        set((s) => ({ divergenceSummary: { ...s.divergenceSummary, [evt.model]: summary } }));
        return;
      }

      case "divergence_models": {
        const { type: _t, queryRunId: _q, t: _time, ...models } = evt;
        set({ divergenceModels: models });
        return;
      }

      case "deflection": {
        set((s) => {
          const next: DeflectionDatum = {
            id: evt.id,
            clusterA: evt.clusterA,
            clusterB: evt.clusterB,
            level: evt.level,
            unitA: evt.unitA,
            unitB: evt.unitB,
            point: evt.point,
            confidence: evt.confidence,
          };
          const idx = s.deflections.findIndex((d) => d.id === evt.id);
          const deflections =
            idx >= 0
              ? s.deflections.map((d, i) => (i === idx ? next : d))
              : [...s.deflections, next];
          return { deflections };
        });
        return;
      }

      case "answer_chunk": {
        set((s) => {
          const answer = mergeAnswer(s.answer, evt.segment);
          return { answer };
        });
        return;
      }

      case "research_document": {
        set((s) => {
          // Dedupe by URL (research() already deduped within one call, but on
          // Go-deeper / reconnect the same URL could arrive again — one entry
          // per URL, first-write-wins on id/title so ordering is stable).
          if (s.researchDocuments.some((d) => d.url === evt.document.url)) return {};
          return { researchDocuments: [...s.researchDocuments, evt.document] };
        });
        return;
      }

      case "done": {
        set((s) => ({
          runState: Object.keys(s.regionStats).length > 0 || s.answer.length > 0 ? "done" : "empty",
          status: { ...s.status, phase: "complete", counts: evt.counts, progress: 1 },
        }));
        return;
      }

      case "error": {
        set({ runState: "error", error: evt.message });
        return;
      }
    }
  },

  finishRun: (result) => set({ runState: result }),
  failRun: (message) => set({ runState: "error", error: message }),
  stop: () =>
    set((s) => {
      if (s.runState !== "streaming" && s.runState !== "connecting") return {};
      const hasData = Object.keys(s.regionStats).length > 0 || s.answer.length > 0;
      return { runState: hasData ? "done" : "idle" };
    }),

  snapshotRun: () => {
    const s = get();
    return {
      regionStats: s.regionStats,
      clusters: s.clusters,
      clusterOrder: s.clusterOrder,
      regions: s.regions,
      regionOrder: s.regionOrder,
      deflections: s.deflections,
      answer: s.answer,
      researchDocuments: s.researchDocuments,
      divergence: s.divergence,
      divergenceSummary: s.divergenceSummary,
      divergenceModels: s.divergenceModels,
      status: s.status,
    };
  },
  restoreRun: (snapshot) => set({ ...snapshot, runState: "connecting", error: null }),
  loadSavedRun: (data) =>
    set({
      queryRunId: data.id,
      query: data.query,
      queryType: data.queryType,
      mode: data.mode,
      provider: data.provider,
      runState: "done",
      error: null,
      legacyRun: !data.regionStats,
      // Older (India-wide, district-level) saved runs have none of the
      // region/divergence fields — default rather than let `undefined` in.
      regionStats: data.regionStats ?? {},
      clusters: data.clusters,
      clusterOrder: data.clusterOrder,
      regions: data.regions ?? {},
      regionOrder: data.regionOrder ?? [],
      deflections: data.deflections,
      answer: data.answer,
      researchDocuments: data.researchDocuments,
      ...normalizeSavedDivergence(data),
      status: data.status,
      selection: NO_SELECTION,
      hoveredClusterId: null,
      deflectionPair: { a: null, b: null },
    }),

  setLayer: (key, value) => set((s) => ({ layers: { ...s.layers, [key]: value } })),
  toggleLayer: (key) => set((s) => ({ layers: { ...s.layers, [key]: !s.layers[key] } })),

  select: (selection) => set({ selection }),
  clearSelection: () => set({ selection: NO_SELECTION }),
  setHoveredCluster: (id) => set({ hoveredClusterId: id }),
  setDeflectionPair: (a, b) => set({ deflectionPair: { a, b } }),

  reset: () =>
    set({
      queryRunId: null,
      query: null,
      queryType: "descriptive",
      mode: "medium",
      provider: "gemma_remote",
      runState: "idle",
      error: null,
      status: IDLE_STATUS,
      legacyRun: false,
      ...EMPTY_DATA,
      selection: NO_SELECTION,
      hoveredClusterId: null,
      deflectionPair: { a: null, b: null },
    }),
}));

/** Saved runs from before per-model divergence stored one model's results unkeyed. */
function normalizeSavedDivergence(
  data: Partial<RunSnapshot> & { provider: LlmProvider },
): Pick<RunSnapshot, "divergence" | "divergenceSummary" | "divergenceModels"> {
  const raw = (data.divergence ?? {}) as Record<string, unknown>;
  const flat = Object.values(raw).some((v) => v && typeof v === "object" && "regionId" in v);
  const rawSummary = data.divergenceSummary as unknown;
  const flatSummary = !!rawSummary && typeof rawSummary === "object" && "matrix" in rawSummary;
  return {
    divergence: flat
      ? { [data.provider]: raw as Record<RegionId, DivergenceRegion> }
      : (data.divergence ?? {}),
    divergenceSummary: flatSummary
      ? { [data.provider]: rawSummary as DivergenceSummary }
      : ((rawSummary as Partial<Record<LlmProvider, DivergenceSummary>> | null) ?? {}),
    divergenceModels: data.divergenceModels ?? null,
  };
}

/**
 * Streaming answer reducer. Consecutive `body` chunks that share region/cluster
 * are concatenated so a paragraph "types in"; a chunk whose text starts with a
 * blank line begins a new paragraph. Headings/recommendations always push.
 */
function mergeAnswer(prev: AnswerSegment[], seg: AnswerSegment): AnswerSegment[] {
  const kind = seg.kind ?? "body";
  const last = prev[prev.length - 1];
  const startsNewPara = /^\s*\n\s*\n/.test(seg.text);
  const cleaned: AnswerSegment = { ...seg, kind, text: seg.text.replace(/^\s*\n\s*\n/, "") };

  if (
    kind === "body" &&
    last &&
    (last.kind ?? "body") === "body" &&
    last.clusterId === seg.clusterId &&
    last.region === seg.region &&
    last.regionId === seg.regionId &&
    !startsNewPara
  ) {
    const joiner = /\s$/.test(last.text) || /^\s/.test(cleaned.text) ? "" : " ";
    const merged: AnswerSegment = { ...last, text: last.text + joiner + cleaned.text };
    return [...prev.slice(0, -1), merged];
  }
  return [...prev, cleaned];
}
