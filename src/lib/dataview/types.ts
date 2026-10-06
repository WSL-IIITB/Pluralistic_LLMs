/**
 * Data View — single source of truth for the streaming event schema and the
 * derived data model.
 *
 * The backend runs a deterministic regression pipeline (no LLM in the loop)
 * over UDISE+/NFHS-5 district data and emits a stream of typed events keyed
 * by a `runId`. The dashboard consumes them progressively. Everything the UI
 * renders is derived from the types in this file, so a new backend only has
 * to emit events that match `DataViewEvent`.
 *
 * Deliberately independent from `src/lib/worldview/types.ts` — no imports
 * either direction. `DistrictId`/`StateCode` are redefined here BY VALUE
 * (same "stateCode-districtCode" convention) so the two features can't force
 * each other into lockstep changes; the only thing they truly share is one
 * map instance (see DeckMap.tsx).
 */

// ─────────────────────────────────────────────────────────────────────────────
// Identifiers & scalars
// ─────────────────────────────────────────────────────────────────────────────

/** One backend pipeline run. */
export type RunId = string;

/**
 * District identifier. Canonical form is `${stateCode}-${censusDistrictCode}`
 * (Census 2011 / LGD codes), e.g. `"09-137"` — same convention as
 * `worldview/types.ts`'s `DistrictId`, but defined locally so this package
 * never imports from `lib/worldview`.
 */
export type DistrictId = string;

/**
 * Whatever string the backend sends as a state's key. Treated as an opaque
 * identifier — it may be a 2-digit Census/LGD code or a bare state name
 * depending on the endpoint, so callers should never assume a particular
 * format and should always key off the value as received.
 */
export type StateCode = string;

/** Stable id for one regression factor (e.g. a UDISE+/NFHS-5 column). */
export type FactorId = string;

/** Thematic grouping a factor is bucketed into (keyword-heuristic, not sourced from a metadata column). */
export type BucketId = "infrastructure" | "digital_ict" | "teacher_profile" | "socio_economic";

export const BUCKET_IDS: readonly BucketId[] = [
  "infrastructure",
  "digital_ict",
  "teacher_profile",
  "socio_economic",
] as const;

/** How aggressively a bucket's factors should be pushed toward their prescribed values. */
export type PriorityLevel = "nil" | "low" | "medium" | "high" | "critical";

export const PRIORITY_LEVELS: readonly PriorityLevel[] = [
  "nil",
  "low",
  "medium",
  "high",
  "critical",
] as const;

// ─────────────────────────────────────────────────────────────────────────────
// Domain data model (what the store accumulates from stream events)
// ─────────────────────────────────────────────────────────────────────────────

/** A district's headline outcome reading (dropout rate for v1's topic). */
export interface DistrictScoreDatum {
  districtId: DistrictId;
  stateCode: StateCode;
  outcomeValue: number;
}

/** A regression factor's identity — label + which theme it's bucketed into. */
export interface FactorDatum {
  factorId: FactorId;
  label: string;
  bucket: BucketId;
}

/** A state's fitted-model summary — average outcome, fit confidence, composite intervention score. */
export interface StateScoreDatum {
  stateCode: StateCode;
  avgOutcome: number;
  confidenceValue: number;
  interventionIndex: number;
}

/** One factor's original vs. prescribed value within a district prescription. */
export interface FactorPrescription {
  factorName: string;
  bucket: BucketId;
  original: number;
  prescribed: number;
}

/** Result of a what-if prescriptive recompute for one district. */
export interface PrescriptionResult {
  districtId: DistrictId;
  targetReduction: number;
  confidenceValue: number;
  factors: FactorPrescription[];
}

/** One factor's sensitivity ratio within a district's profile. */
export interface DistrictFactorSensitivity {
  factorName: string;
  bucket: BucketId;
  sensitivityPct: number;
}

/** District Profile: per-factor sensitivity ratios (sum to 100%) plus the headline outcome. */
export interface DistrictProfile {
  districtId: DistrictId;
  stateCode: StateCode;
  outcomeValue: number;
  factors: DistrictFactorSensitivity[];
}

/** One factor's share of a budget allocation. */
export interface BudgetShare {
  factorName: string;
  bucket: BucketId;
  amount: number;
}

/** Result of splitting a state's entered budget across factors. */
export interface BudgetAllocationResult {
  stateCode: StateCode;
  totalBudget: number;
  shares: BudgetShare[];
}

/** Which kind of area a fetched verdict narrative is about. */
export type VerdictAreaKind = "district" | "state";

/**
 * `GET /district/{id}/verdict` / `GET /state/{code}/verdict` — a real,
 * LLM-generated (gemma_remote by default), multi-paragraph natural-language
 * narrative explaining WHY children in this specific area are dropping out
 * of secondary school, grounded in that area's own real computed data (see
 * backend/app/dataview/verdict.py). `verdict` is plain text with paragraphs
 * separated by "\n\n" — render it split on that, never as raw markdown.
 * `areaId`/`areaKind` echo back exactly what was requested, so a caller can
 * confirm a fetched result still matches the CURRENT selection before
 * rendering it (selection can change while a slow LLM call is in flight).
 */
export interface VerdictResult {
  areaId: string;
  areaKind: VerdictAreaKind;
  areaName: string;
  stateName: string;
  verdict: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Streaming event schema
// ─────────────────────────────────────────────────────────────────────────────

interface EventBase {
  runId: RunId;
}

/**
 * A regression factor was defined (identity + bucket) for one state's
 * fitted model. The backend emits one `factor_defined` event per
 * (state, factor) pair it fit — the same factor name can recur across
 * multiple states' events since each state fits its own small active-factor
 * set (see the plan's per-state-modeling note) — so `stateCode` here is NOT
 * incidental bookkeeping: it's what lets the UI know which factors are
 * actually valid to query for a given state (see `store.ts`'s
 * `factorsByState`). Querying a factor/state pair the backend never fit
 * 404s.
 */
export interface FactorDefinedEvent extends EventBase {
  type: "factor_defined";
  factorId: FactorId;
  label: string;
  bucket: BucketId;
  stateCode: StateCode;
  r2: number;
}

/** A district's headline outcome value was scored. */
export interface DistrictScoredEvent extends EventBase {
  type: "district_scored";
  districtId: DistrictId;
  stateCode: StateCode;
  outcomeValue: number;
}

/** A state's fitted-model summary was computed. */
export interface StateScoredEvent extends EventBase {
  type: "state_scored";
  stateCode: StateCode;
  avgOutcome: number;
  confidenceValue: number;
  interventionIndex: number;
}

/** Terminal success event. */
export interface DataViewDoneEvent extends EventBase {
  type: "done";
  districtCount: number;
  factorCount: number;
  stateCount: number;
}

/** Terminal error event (also used for transport-level failures). */
export interface DataViewErrorEvent extends EventBase {
  type: "error";
  message: string;
}

/** The full discriminated union the Data View stream yields. */
export type DataViewEvent =
  | FactorDefinedEvent
  | DistrictScoredEvent
  | StateScoredEvent
  | DataViewDoneEvent
  | DataViewErrorEvent;

export type DataViewEventType = DataViewEvent["type"];
