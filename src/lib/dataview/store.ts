/**
 * Data View store (Zustand).
 *
 * Holds everything derived from the one-time nationwide bootstrap load —
 * districts→outcome, factor definitions, per-state model summaries — plus
 * the interactive slider/selection state that drives the synchronous REST
 * recompute endpoints (prescription, sensitivity, budget).
 *
 * A separate store from `useWorldviewStore` by design (see the plan's
 * "Architecture decisions" — Story View and Data View share only the map
 * instance and the DistrictId/StateCode/Selection shapes, copied by value,
 * not cross-imported).
 */

import { create } from "zustand";

import { getDistrictPrescription, getVerdict, postBudgetAllocation } from "./api";
import { openDataViewStream } from "./stream/sseStream";
import {
  type BucketId,
  type BudgetAllocationResult,
  type DataViewEvent,
  type DistrictId,
  type DistrictScoreDatum,
  type FactorDatum,
  type FactorId,
  type PriorityLevel,
  type PrescriptionResult,
  type StateCode,
  type StateScoreDatum,
  type VerdictResult,
} from "./types";

export type DataViewLoadState = "idle" | "loading" | "ready" | "error";

export type DataViewColorMode = "dropoutRate" | "interventionIndex";

/**
 * Which of Data View's two pages is showing — "Verdict" (map + per-state
 * top-5-factors table + factor cross-filter + the real LLM-generated verdict
 * narrative for whatever's selected) or "Intervention & Budget" (bucket
 * sliders, Original-vs-Prescribed table, budget allocation). Mirrors the
 * reference LKI/IIIT-B dashboard's guided two-page flow, switched by an
 * explicit forward/back control — NEVER auto-switched as a side effect of a
 * map click/selection change, which is why this is its own field rather
 * than folded into `selection` below (selection MUST persist across a
 * toggle in either direction).
 */
export type DataViewActiveView = "verdict" | "intervention";

export type DataViewSelection =
  | { kind: "district"; id: DistrictId }
  | { kind: "state"; id: StateCode }
  | { kind: null; id: null };

const NO_SELECTION: DataViewSelection = { kind: null, id: null };

const DEFAULT_BUCKET_PRIORITIES: Record<BucketId, PriorityLevel> = {
  infrastructure: "medium",
  digital_ict: "medium",
  teacher_profile: "medium",
  socio_economic: "medium",
};

export interface DataViewStore {
  loadState: DataViewLoadState;
  error: string | null;

  // ── accumulated bootstrap data ──────────────────────────────────────────
  districts: Record<DistrictId, DistrictScoreDatum>;
  factors: Record<FactorId, FactorDatum>;
  /** Which factors are actually active (fitted) for each state — a factor
   * name can recur across multiple states' `factor_defined` events, so this
   * is what lets a caller know a given (factorId, stateCode) pair is real.
   * Built from the same stream `factors` is built from; see
   * {@link FactorDefinedEvent}. */
  factorsByState: Record<StateCode, Record<FactorId, true>>;
  /**
   * Per-(state, factor) fit quality (`FactorDefinedEvent.r2`), keyed the same
   * way as `factorsByState` above. A separate field rather than widening
   * `factorsByState`'s value type: that field's `true`-valued shape is a
   * presence flag other code depends on staying exactly that — this is
   * purely additive, so a real per-state "top factors" ranking (see
   * `selectors.ts`'s `topFactorsForState`/`statesSharingFactor`) has
   * something to sort by.
   */
  factorR2ByState: Record<StateCode, Record<FactorId, number>>;
  /** Keyed verbatim by whatever string the backend sends as stateCode — see {@link StateCode}. */
  stateScores: Record<StateCode, StateScoreDatum>;

  // ── view state ───────────────────────────────────────────────────────────
  colorMode: DataViewColorMode;
  selection: DataViewSelection;
  /** Deliberately independent of `selection` — see {@link DataViewActiveView}. */
  activeDataView: DataViewActiveView;

  // ── prescriptive/budget interactive state ───────────────────────────────
  targetReduction: number;
  bucketPriorities: Record<BucketId, PriorityLevel>;
  districtPrescription: PrescriptionResult | null;
  budgetResult: BudgetAllocationResult | null;

  // ── verdict narrative (Verdict page) ────────────────────────────────────
  /** Last-fetched verdict — check `verdict.areaId`/`areaKind` against the
   * CURRENT selection before rendering it (a slow LLM call can resolve
   * after the user has already selected something else; see
   * `fetchVerdict`'s own request-sequencing note below). */
  verdict: VerdictResult | null;
  verdictLoading: boolean;
  /** Set when the last `fetchVerdict` call failed (including a genuine
   * timeout/abort) — cleared at the start of every new call, mirroring
   * every other `*Error` field's contract in this store. */
  verdictError: string | null;

  // ── actions ─────────────────────────────────────────────────────────────
  /** Idempotent: a no-op if a bootstrap is already loading or has completed. */
  bootstrap(): void;
  applyEvent(evt: DataViewEvent): void;
  select(selection: DataViewSelection): void;
  clearSelection(): void;
  setColorMode(mode: DataViewColorMode): void;
  /** Explicit user action (the Verdict / Intervention & Budget toggle) —
   * never called as a side effect of `select`/`clearSelection` above. */
  setActiveDataView(view: DataViewActiveView): void;
  setTargetReduction(v: number): void;
  setBucketPriority(bucket: BucketId, level: PriorityLevel): void;
  /** Debouncing is the CALLER's job — this is a plain fetch-and-set. */
  fetchDistrictPrescription(districtId: DistrictId): Promise<void>;
  fetchBudgetAllocation(stateCode: StateCode, totalBudget: number): Promise<void>;
  /**
   * Fetches the real LLM-backed verdict narrative for one area. Self-guards
   * against out-of-order resolution (a slow call for a PREVIOUS selection
   * resolving after a newer one was already requested) via an internal
   * monotonic sequence number — the caller doesn't need to debounce or
   * track staleness itself, just call this on every selection change.
   */
  fetchVerdict(areaKind: VerdictResult["areaKind"], id: DistrictId | StateCode): Promise<void>;
}

/** Guards `fetchVerdict` against an out-of-order resolve — module-scoped
 * (one store instance in practice), incremented on every call so only the
 * MOST RECENTLY requested call is allowed to write its result/loading state. */
let verdictRequestSeq = 0;

export const useDataViewStore = create<DataViewStore>((set, get) => ({
  loadState: "idle",
  error: null,

  districts: {},
  factors: {},
  factorsByState: {},
  factorR2ByState: {},
  stateScores: {},

  colorMode: "dropoutRate",
  selection: NO_SELECTION,
  activeDataView: "verdict",

  targetReduction: 0.2,
  bucketPriorities: { ...DEFAULT_BUCKET_PRIORITIES },
  districtPrescription: null,
  budgetResult: null,

  verdict: null,
  verdictLoading: false,
  verdictError: null,

  bootstrap: () => {
    const { loadState } = get();
    if (loadState === "loading" || loadState === "ready") return;
    set({ loadState: "loading", error: null });
    openDataViewStream({
      onEvent: (event) => get().applyEvent(event),
      onError: (message) => set({ loadState: "error", error: message }),
      onClose: () => {},
    });
  },

  applyEvent: (evt) => {
    switch (evt.type) {
      case "factor_defined": {
        set((s) => ({
          factors: {
            ...s.factors,
            [evt.factorId]: { factorId: evt.factorId, label: evt.label, bucket: evt.bucket },
          },
          factorsByState: {
            ...s.factorsByState,
            [evt.stateCode]: { ...s.factorsByState[evt.stateCode], [evt.factorId]: true },
          },
          factorR2ByState: {
            ...s.factorR2ByState,
            [evt.stateCode]: { ...s.factorR2ByState[evt.stateCode], [evt.factorId]: evt.r2 },
          },
        }));
        return;
      }

      case "district_scored": {
        set((s) => ({
          districts: {
            ...s.districts,
            [evt.districtId]: {
              districtId: evt.districtId,
              stateCode: evt.stateCode,
              outcomeValue: evt.outcomeValue,
            },
          },
        }));
        return;
      }

      case "state_scored": {
        set((s) => ({
          stateScores: {
            ...s.stateScores,
            [evt.stateCode]: {
              stateCode: evt.stateCode,
              avgOutcome: evt.avgOutcome,
              confidenceValue: evt.confidenceValue,
              interventionIndex: evt.interventionIndex,
            },
          },
        }));
        return;
      }

      case "done": {
        set({ loadState: "ready" });
        return;
      }

      case "error": {
        set({ loadState: "error", error: evt.message });
        return;
      }
    }
  },

  select: (selection) => set({ selection }),
  clearSelection: () => set({ selection: NO_SELECTION }),
  setColorMode: (mode) => set({ colorMode: mode }),
  setActiveDataView: (view) => set({ activeDataView: view }),
  setTargetReduction: (v) => set({ targetReduction: v }),
  setBucketPriority: (bucket, level) =>
    set((s) => ({ bucketPriorities: { ...s.bucketPriorities, [bucket]: level } })),

  fetchDistrictPrescription: async (districtId) => {
    try {
      const { targetReduction, bucketPriorities } = get();
      const result = await getDistrictPrescription(districtId, targetReduction, bucketPriorities);
      set({ districtPrescription: result });
    } catch (err) {
      console.warn("Failed to fetch district prescription:", err);
    }
  },

  fetchVerdict: async (areaKind, id) => {
    // Already have this exact area's verdict cached — skip the network
    // round-trip entirely. Without this, toggling Verdict -> Intervention &
    // Budget -> Verdict remounts the Verdict page (DataViewPanels only ever
    // mounts one of the two pages at a time), which re-runs this effect on
    // mount and would otherwise throw away an already-fetched narrative and
    // force the user through another real, possibly 15-40+s LLM call for
    // IDENTICAL content. A genuine selection change always calls this with
    // a different (areaKind, id), so this only short-circuits true no-ops —
    // a failed previous attempt (verdict left unset/mismatched) still
    // retries normally.
    const cached = get().verdict;
    if (cached && cached.areaKind === areaKind && cached.areaId === id) return;

    const seq = ++verdictRequestSeq;
    set({ verdictLoading: true, verdictError: null });
    try {
      const result = await getVerdict(areaKind, id);
      if (seq !== verdictRequestSeq) return; // superseded by a newer selection's call — drop this stale result
      set({ verdict: result, verdictLoading: false });
    } catch (err) {
      if (seq !== verdictRequestSeq) return;
      console.warn("Failed to fetch verdict:", err);
      set({
        verdictLoading: false,
        verdictError: err instanceof Error ? err.message : "Failed to load verdict.",
      });
    }
  },

  fetchBudgetAllocation: async (stateCode, totalBudget) => {
    try {
      const result = await postBudgetAllocation(stateCode, totalBudget, get().bucketPriorities);
      set({ budgetResult: result });
    } catch (err) {
      console.warn("Failed to fetch budget allocation:", err);
    }
  },
}));
