/**
 * Worldview run store (Zustand).
 *
 * Holds everything derived from one query run — posts→districts, clusters,
 * deflections, the consolidated answer, and progress — keyed by `queryRunId`.
 *
 * The store is designed so a re-run ("Go deeper") MERGES into the existing
 * state rather than replacing it: call `prepareRun({ deeper: true })` and the
 * accumulated districts/clusters/answer are kept while new events refine them.
 */

import { create } from "zustand";

import {
  type AnswerSegment,
  type ClusterDatum,
  type ClusterId,
  type CollectionCounts,
  type DeflectionDatum,
  type DistrictDatum,
  type DistrictId,
  type LlmProvider,
  type QueryRunId,
  type QueryType,
  type RegionDatum,
  type RegionId,
  type ResearchDocument,
  type ResearchMode,
  type RunPhase,
  type StateCode,
  type WorldviewEvent,
  resolveClusterStateCode,
} from "./types";
import { paletteColor, paletteColorForRegion, paletteColorForState } from "./palette";

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
  splitStates: boolean;
}

export type Selection =
  | { kind: "district"; id: DistrictId }
  | { kind: "state"; id: StateCode }
  | { kind: null; id: null };

/** Accumulated-data slice, captured before a pass starts so a reconnect can rewind to it. */
export interface RunSnapshot {
  districts: Record<DistrictId, DistrictDatum>;
  clusters: Record<ClusterId, ClusterDatum>;
  clusterOrder: ClusterId[];
  /** extrahigh mode only (empty for basic/medium/high). Order is discovery
   *  order — the first region's clusters get index 0's hue, etc. — see
   *  {@link paletteColorForRegion}. */
  regions: Record<RegionId, RegionDatum>;
  regionOrder: RegionId[];
  deflections: DeflectionDatum[];
  answer: AnswerSegment[];
  researchDocuments: ResearchDocument[];
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

  // ── accumulated data ────────────────────────────────────────────────────────
  districts: Record<DistrictId, DistrictDatum>;
  clusters: Record<ClusterId, ClusterDatum>;
  clusterOrder: ClusterId[];
  /** extrahigh mode only (empty for basic/medium/high) — see {@link RunSnapshot.regions}. */
  regions: Record<RegionId, RegionDatum>;
  regionOrder: RegionId[];
  deflections: DeflectionDatum[];
  answer: AnswerSegment[];
  /** Web-search-grounded sources gathered by the research stage, in id order,
   *  deduped by URL. Rendered as the "Sources" section of the consolidated
   *  answer panel; also referenced from AnswerSegment.citations (1-based ids). */
  researchDocuments: ResearchDocument[];

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

/** How many clusters already exist for `stateCode` (extrahigh only) — used to
 * pick the next lightness step for a newly-discovered cluster within that
 * state. O(order.length), but only runs once per newly-discovered cluster
 * id (ensureCluster early-returns for known ids), not per event — negligible
 * even at extrahigh's ~190-total-cluster scale. */
function countForState(
  clusters: Record<ClusterId, ClusterDatum>,
  order: readonly ClusterId[],
  stateCode: StateCode,
): number {
  let count = 0;
  for (const id of order) {
    if (clusters[id]?.stateCode === stateCode) count++;
  }
  return count;
}

/** Same role as `countForState`, but for regions — how many clusters already
 * exist for `regionId` (extrahigh only), used to pick the next lightness
 * step for a newly-discovered cluster within that region. */
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

/** Ensure a cluster stub exists so events can arrive in any order. `mode`
 * gates whether a resolvable state/region should get its own per-group
 * colour (extrahigh) or the shared global palette (basic/medium/high) —
 * mode as a safety gate, the resolved id as the actual data source, so a
 * stray colon in a non-extrahigh id can never accidentally trigger
 * per-state colouring. A resolvable `regionId` takes priority over
 * `stateCode` (region is the authoritative extrahigh grouping — see
 * ClusterDatum's doc comments — `stateCode` is now just a representative,
 * transitional value on a region-scoped cluster). */
function ensureCluster(
  clusters: Record<ClusterId, ClusterDatum>,
  order: ClusterId[],
  regionOrder: readonly RegionId[],
  id: ClusterId,
  mode: ResearchMode,
  explicitStateCode?: StateCode,
  explicitRegionId?: RegionId,
): ClusterDatum {
  const existing = clusters[id];
  if (existing) return existing;
  const stateCode =
    mode === "extrahigh" ? resolveClusterStateCode(explicitStateCode, id) : undefined;
  const regionId = mode === "extrahigh" ? explicitRegionId : undefined;

  let color: ReturnType<typeof paletteColor>;
  if (regionId) {
    // Discovery-order index, not a hash of the id string — see
    // paletteColorForRegion's doc comment for why.
    const regionIndex = Math.max(0, regionOrder.indexOf(regionId));
    color = paletteColorForRegion(regionIndex, countForRegion(clusters, order, regionId));
  } else if (stateCode) {
    color = paletteColorForState(stateCode, countForState(clusters, order, stateCode));
  } else {
    color = paletteColor(order.length);
  }

  const stub: ClusterDatum = {
    id,
    label: id,
    color,
    ...(stateCode ? { stateCode } : {}),
    ...(regionId ? { regionId } : {}),
    representativePosts: [],
    postCount: 0,
  };
  clusters[id] = stub;
  order.push(id);
  return stub;
}

export const useWorldviewStore = create<WorldviewStore>((set, get) => ({
  queryRunId: null,
  query: null,
  queryType: "descriptive",
  mode: "medium",
  provider: "gemma_remote",
  runState: "idle",
  error: null,
  status: IDLE_STATUS,

  districts: {},
  clusters: {},
  clusterOrder: [],
  regions: {},
  regionOrder: [],
  deflections: [],
  answer: [],
  researchDocuments: [],

  layers: { columns: true, links: true, splitStates: true },
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
      status: { ...IDLE_STATUS, ticker: `Sourcing posts for “${query}”…`, progress: 0.01 },
      districts: {},
      clusters: {},
      clusterOrder: [],
      regions: {},
      regionOrder: [],
      deflections: [],
      answer: [],
      researchDocuments: [],
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
          const prev = ensureCluster(
            clusters,
            order,
            s.regionOrder,
            evt.clusterId,
            s.mode,
            evt.stateCode,
            evt.regionId,
          );
          clusters[evt.clusterId] = {
            ...prev,
            label: evt.label,
            // Backend colour stays authoritative for basic/medium/high;
            // extrahigh keeps the frontend-computed per-region (or per-state,
            // for older saved runs predating region-inference) colour instead
            // (the backend's own 6-color-cycle-per-scope value would collide
            // across different regions/states — see palette.ts's
            // paletteColorForRegion/paletteColorForState).
            color: s.mode === "extrahigh" ? prev.color : evt.color,
            ...(evt.summary !== undefined ? { summary: evt.summary } : {}),
            representativePosts: evt.representativePosts ?? prev.representativePosts,
          };
          return { clusters, clusterOrder: order };
        });
        return;
      }

      case "district_resolved": {
        set((s) => {
          const districts = { ...s.districts };
          const clusters = { ...s.clusters };
          const order = [...s.clusterOrder];
          ensureCluster(
            clusters,
            order,
            s.regionOrder,
            evt.clusterId,
            s.mode,
            evt.stateCode,
            evt.regionId,
          );

          const prev = districts[evt.districtId];
          const clusterVolumes: Record<ClusterId, number> = { ...(prev?.clusterVolumes ?? {}) };
          clusterVolumes[evt.clusterId] = (clusterVolumes[evt.clusterId] ?? 0) + evt.volume;
          const dominant = dominantCluster(clusterVolumes) ?? evt.clusterId;
          // Only adopt this event's confidence/method/fallback when it describes
          // the (possibly newly-recomputed) dominant cluster — otherwise a small
          // update to a minority cluster would overwrite the dominant reading's stats.
          const describesDominant = evt.clusterId === dominant;

          const samplePosts = evt.samplePosts
            ? [...(prev?.samplePosts ?? []), ...evt.samplePosts].slice(-6)
            : prev?.samplePosts;

          districts[evt.districtId] = {
            districtId: evt.districtId,
            stateCode: evt.stateCode,
            // Fixed for the whole run (a district belongs to exactly one
            // region, unlike confidence/method below) — no dominant-cluster
            // gating needed.
            ...(evt.regionId
              ? { regionId: evt.regionId }
              : prev?.regionId
                ? { regionId: prev.regionId }
                : {}),
            clusterId: dominant,
            confidence: describesDominant ? evt.confidence : (prev?.confidence ?? evt.confidence),
            volume: (prev?.volume ?? 0) + evt.volume,
            method: describesDominant ? evt.method : (prev?.method ?? evt.method),
            isStateFallback: describesDominant
              ? (evt.isStateFallback ?? evt.method === "state_fallback")
              : (prev?.isStateFallback ?? false),
            clusterVolumes,
            ...(samplePosts ? { samplePosts } : {}),
          };

          // Accrue post volume onto the cluster total.
          const cl = clusters[evt.clusterId];
          if (cl) clusters[evt.clusterId] = { ...cl, postCount: cl.postCount + evt.volume };

          return { districts, clusters, clusterOrder: order };
        });
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
          runState: s.districts && Object.keys(s.districts).length > 0 ? "done" : "empty",
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
      const hasData = Object.keys(s.districts).length > 0;
      return { runState: hasData ? "done" : "idle" };
    }),

  snapshotRun: () => {
    const s = get();
    return {
      districts: s.districts,
      clusters: s.clusters,
      clusterOrder: s.clusterOrder,
      regions: s.regions,
      regionOrder: s.regionOrder,
      deflections: s.deflections,
      answer: s.answer,
      researchDocuments: s.researchDocuments,
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
      districts: data.districts,
      clusters: data.clusters,
      clusterOrder: data.clusterOrder,
      // Older saved runs predate region-inference and won't have these
      // fields in their persisted JSON at all (backend never validates the
      // payload shape it stores — see run_history.py) — default rather than
      // let `undefined` slip through the store's Record<...>/array types.
      regions: data.regions ?? {},
      regionOrder: data.regionOrder ?? [],
      deflections: data.deflections,
      answer: data.answer,
      researchDocuments: data.researchDocuments,
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
      districts: {},
      clusters: {},
      clusterOrder: [],
      regions: {},
      regionOrder: [],
      deflections: [],
      answer: [],
      researchDocuments: [],
      selection: NO_SELECTION,
      hoveredClusterId: null,
      deflectionPair: { a: null, b: null },
    }),
}));

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
    !startsNewPara
  ) {
    const merged: AnswerSegment = { ...last, text: last.text + cleaned.text };
    return [...prev.slice(0, -1), merged];
  }
  return [...prev, cleaned];
}
