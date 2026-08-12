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
  type ResearchDocument,
  type ResearchMode,
  type RunPhase,
  type StateCode,
  type WorldviewEvent,
  resolveClusterStateCode,
} from "./types";
import { paletteColor, paletteColorForState } from "./palette";

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
  deflections: DeflectionDatum[];
  answer: AnswerSegment[];
  researchDocuments: ResearchDocument[];
  status: StatusSnapshot;
}

const EMPTY_COUNTS: CollectionCounts = {
  postsCollected: 0,
  districtsResolved: 0,
  clustersFound: 0,
  deflectionsFound: 0,
  sourcesGathered: 0,
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

/** Ensure a cluster stub exists so events can arrive in any order. `mode`
 * gates whether a resolvable state code should get its own per-state colour
 * (extrahigh) or the shared global palette (basic/medium/high) — mode as a
 * safety gate, the resolved state code as the actual data source, so a
 * stray colon in a non-extrahigh id can never accidentally trigger
 * per-state colouring. */
function ensureCluster(
  clusters: Record<ClusterId, ClusterDatum>,
  order: ClusterId[],
  id: ClusterId,
  mode: ResearchMode,
  explicitStateCode?: StateCode,
): ClusterDatum {
  const existing = clusters[id];
  if (existing) return existing;
  const stateCode =
    mode === "extrahigh" ? resolveClusterStateCode(explicitStateCode, id) : undefined;
  const color = stateCode
    ? paletteColorForState(stateCode, countForState(clusters, order, stateCode))
    : paletteColor(order.length);
  const stub: ClusterDatum = {
    id,
    label: id,
    color,
    ...(stateCode ? { stateCode } : {}),
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
  provider: "azure_anthropic",
  runState: "idle",
  error: null,
  status: IDLE_STATUS,

  districts: {},
  clusters: {},
  clusterOrder: [],
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
      provider: "azure_anthropic",
      status: { ...IDLE_STATUS, ticker: `Sourcing posts for “${query}”…`, progress: 0.01 },
      districts: {},
      clusters: {},
      clusterOrder: [],
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

      case "cluster_defined": {
        set((s) => {
          const clusters = { ...s.clusters };
          const order = [...s.clusterOrder];
          const prev = ensureCluster(clusters, order, evt.clusterId, s.mode, evt.stateCode);
          clusters[evt.clusterId] = {
            ...prev,
            label: evt.label,
            // Backend colour stays authoritative for basic/medium/high;
            // extrahigh keeps the frontend-computed per-state colour instead
            // (the backend's own 6-color-cycle-per-state value would collide
            // across different states — see palette.ts's paletteColorForState).
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
          ensureCluster(clusters, order, evt.clusterId, s.mode, evt.stateCode);

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
      deflections: s.deflections,
      answer: s.answer,
      researchDocuments: s.researchDocuments,
      status: s.status,
    };
  },
  restoreRun: (snapshot) => set({ ...snapshot, runState: "connecting", error: null }),

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
      provider: "azure_anthropic",
      runState: "idle",
      error: null,
      status: IDLE_STATUS,
      districts: {},
      clusters: {},
      clusterOrder: [],
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
