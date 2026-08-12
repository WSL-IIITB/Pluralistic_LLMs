/**
 * Worldview Explorer — single source of truth for the streaming event schema
 * and the derived data model.
 *
 * The backend agent graph (LangGraph) emits a stream of typed events keyed by a
 * `queryRunId`. The dashboard consumes them progressively. Everything the UI
 * renders is derived from the types in this file, so a new backend only has to
 * emit events that match `WorldviewEvent`.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Identifiers & scalars
// ─────────────────────────────────────────────────────────────────────────────

/** A single agent-graph invocation. Multiple runs (e.g. "Go deeper") share one. */
export type QueryRunId = string;

/**
 * District identifier. Canonical form is `${stateCode}-${censusDistrictCode}`
 * (Census 2011 / LGD codes), e.g. `"09-137"`. Use {@link makeDistrictId} to
 * build one so the map loader and the stream stay in sync.
 */
export type DistrictId = string;

/** Census 2011 / LGD 2-digit state code, e.g. `"09"` for Uttar Pradesh. */
export type StateCode = string;

/** Stable slug for a viewpoint cluster, e.g. `"rama"`. */
export type ClusterId = string;

/** deck.gl RGB(A) colour, channels 0–255. Alpha optional (defaults opaque). */
export type RGBAColor = [number, number, number] | [number, number, number, number];

/** Whether the answer is a neutral description or a policy recommendation. */
export type QueryType = "descriptive" | "policy";

/**
 * How thorough a run is. Geographic coverage is always full regardless of
 * mode (every Indian state/region gets surveyed) — for basic/medium/high,
 * mode instead controls the VOLUME of sources gathered per state/framing and
 * how much effort the research stage spends per angle. "extrahigh" is
 * qualitatively different, not just "more of the same": the backend clusters
 * each state's posts independently instead of pooling every state into one
 * global clustering pass, so a single run can produce 60-190 distinct
 * viewpoint clusters instead of today's 2-6. Mirrors the backend's
 * `reasoning_modes.ResearchMode`.
 */
export type ResearchMode = "basic" | "medium" | "high" | "extrahigh";

export const RESEARCH_MODES: readonly ResearchMode[] = [
  "basic",
  "medium",
  "high",
  "extrahigh",
] as const;

/**
 * "Go deeper"'s escalation ladder — deliberately capped at "high", NOT the
 * full {@link RESEARCH_MODES} list. extrahigh is a qualitatively different
 * pipeline (per-state clustering, ~3x the LLM call volume, see ResearchMode's
 * doc comment), not just "more of the same," so it must only be reached by
 * deliberate manual selection in the mode toggle group — never as a side
 * effect of repeatedly clicking "Go deeper" from a "high" run.
 */
const ESCALATION_ORDER: readonly ResearchMode[] = ["basic", "medium", "high"] as const;

/** One step more thorough, capped at "high" (see {@link ESCALATION_ORDER}) —
 * what "Go deeper" does now. A run already at "extrahigh" stays there. */
export function escalateMode(mode: ResearchMode): ResearchMode {
  const idx = ESCALATION_ORDER.indexOf(mode);
  if (idx === -1) return mode;
  return ESCALATION_ORDER[Math.min(idx + 1, ESCALATION_ORDER.length - 1)] ?? mode;
}

/**
 * Which LLM backend answers a run. "openai" is selectable in the type but the
 * UI keeps it disabled (that account is out of credits); "gemma_local" and
 * "mistral_local" run entirely on-device via Ollama, zero per-call cost.
 * Mirrors the backend's `reasoning_modes.LlmProvider`.
 */
export type LlmProvider = "azure_anthropic" | "openai" | "gemma_local" | "mistral_local";

export const LLM_PROVIDERS: readonly LlmProvider[] = [
  "azure_anthropic",
  "openai",
  "gemma_local",
  "mistral_local",
] as const;

/** Confidence in a district's geolocation + cluster assignment. */
export type ConfidenceTier = "high" | "medium" | "low";

/**
 * How a post was resolved to a district, in priority order. Mirrors the
 * backend's hierarchical resolver (city-subreddit → place NER → script/language
 * → LLM geolocation), with a district→state→unresolved fallback.
 */
export type ResolutionMethod =
  | "city_subreddit"
  | "place_ner"
  | "script_language"
  | "llm_geolocation"
  | "state_fallback"
  | "unresolved";

/** The two viewpoints in a deflection can co-occur at different scales. */
export type DeflectionLevel =
  "intra-district" | "inter-district" | "intra-state" | "inter-state" | "inter-region";

/** Coarse stage of the run, drives the ticker and progress semantics. */
export type RunPhase =
  | "sourcing"
  | "researching"
  | "resolving"
  | "clustering"
  | "deflecting"
  | "synthesizing"
  | "complete";

export const CONFIDENCE_TIERS: readonly ConfidenceTier[] = ["high", "medium", "low"] as const;

// ─────────────────────────────────────────────────────────────────────────────
// Domain data model (what the store accumulates from events)
// ─────────────────────────────────────────────────────────────────────────────

/** A paraphrased sample post. We never surface verbatim user content. */
export interface SamplePost {
  id: string;
  platform: "reddit" | "youtube";
  /** Paraphrased gist — safe to display, not the original text. */
  paraphrase: string;
  clusterId?: ClusterId;
  /** Link back to the original post, when the source provided one. */
  url?: string;
}

/** A distinct viewpoint discovered by the clustering stage. */
export interface ClusterDatum {
  id: ClusterId;
  label: string;
  /** Categorical colour used for both the map columns and the legend swatch. */
  color: RGBAColor;
  /** One-line gloss of what this viewpoint holds. */
  summary?: string;
  /** Paraphrased representative posts for the click-through / traceability. */
  representativePosts: SamplePost[];
  /** Running count of posts attributed to this cluster. */
  postCount: number;
  /**
   * extrahigh mode only (undefined for basic/medium/high, whose clusters are
   * global/unscoped) — which state this cluster belongs to. Set once, at
   * stub-creation time, from the id-scoping convention (see
   * {@link parseStateScopedClusterId}) or an explicit event field; never
   * recomputed afterward.
   */
  stateCode?: StateCode;
}

/** A district's resolved state: which viewpoint dominates and how sure we are. */
export interface DistrictDatum {
  districtId: DistrictId;
  stateCode: StateCode;
  /** Dominant cluster for the district (null while still unresolved). */
  clusterId: ClusterId | null;
  confidence: ConfidenceTier;
  /** Post volume — drives 3D column height. */
  volume: number;
  method: ResolutionMethod;
  /** True when the reading fell back to the parent state's aggregate. */
  isStateFallback: boolean;
  /** Optional per-cluster breakdown for richer click-through / entropy. */
  clusterVolumes?: Record<ClusterId, number>;
  samplePosts?: SamplePost[];
}

/** The single load-bearing proposition two viewpoints fork on. */
export interface DeflectionDatum {
  id: string;
  /** Cluster on side A / side B (the two co-occurring viewpoints). */
  clusterA: ClusterId;
  clusterB: ClusterId;
  level: DeflectionLevel;
  /** Human-readable geographic anchors, e.g. "North" / "South", or districts. */
  unitA: string;
  unitB: string;
  /** The point of deflection: the proposition the two views disagree on. */
  point: string;
  confidence: ConfidenceTier;
}

/**
 * A segment of the consolidated answer. Segments carry an optional `clusterId`
 * so a claim can be traced back to the viewpoint/region it came from.
 */
export interface AnswerSegment {
  text: string;
  clusterId?: ClusterId;
  /** Region label for policy-mode differentiated recommendations. */
  region?: string;
  /**
   * How this segment renders:
   *  - `tldr`           one-sentence takeaway, pinned at the top of the panel
   *  - `recommendation` a tight scannable bullet
   *  - `detail`         long-form prose, collapsed behind a "Full analysis" toggle
   *  - `heading`/`body` legacy inline forms (still rendered; used by the mock)
   */
  kind?: "tldr" | "heading" | "body" | "recommendation" | "detail";
  /** 1-based ids into the run's ResearchDocument list, if this segment cites research. */
  citations?: number[];
}

/**
 * One external source gathered by the research stage. `id` is 1-based ordering
 * within a run and matches the values in `AnswerSegment.citations`.
 */
export interface ResearchDocument {
  id: number;
  url: string;
  title: string;
  domain: string;
  snippet: string;
}

/** Live counts surfaced by `status` events. */
export interface CollectionCounts {
  postsCollected: number;
  districtsResolved: number;
  clustersFound: number;
  deflectionsFound: number;
  /** Total web sources gathered so far by the research stage (0 if not run yet). */
  sourcesGathered: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Streaming event schema
// ─────────────────────────────────────────────────────────────────────────────

interface EventBase {
  queryRunId: QueryRunId;
  /** Milliseconds since the run started (monotonic), for ordering/debug. */
  t?: number;
}

/** Emitted once at the top of a run. Establishes id + query semantics. */
export interface QueryStartedEvent extends EventBase {
  type: "query_started";
  query: string;
  queryType: QueryType;
  /** Basic/medium/high — see {@link ResearchMode}. Escalated on "Go deeper". */
  mode: ResearchMode;
  /** Which LLM backend actually ran this query — see {@link LlmProvider}. */
  provider: LlmProvider;
}

/** Ticker text + rolling counts + coarse phase + progress fraction (0–1). */
export interface StatusEvent extends EventBase {
  type: "status";
  ticker: string;
  phase: RunPhase;
  counts: CollectionCounts;
  /** 0–1 collection progress. */
  progress: number;
}

/** A post batch resolved to a district with a dominant cluster + confidence. */
export interface DistrictResolvedEvent extends EventBase {
  type: "district_resolved";
  districtId: DistrictId;
  stateCode: StateCode;
  clusterId: ClusterId;
  confidence: ConfidenceTier;
  /** Incremental volume added by this event (store accumulates). */
  volume: number;
  method: ResolutionMethod;
  isStateFallback?: boolean;
  samplePosts?: SamplePost[];
}

/** A new viewpoint cluster was defined (or an existing one refined). */
export interface ClusterDefinedEvent extends EventBase {
  type: "cluster_defined";
  clusterId: ClusterId;
  label: string;
  color: RGBAColor;
  summary?: string;
  representativePosts?: SamplePost[];
  /** extrahigh mode only — see {@link ClusterDatum.stateCode}. */
  stateCode?: StateCode;
}

/** A point of deflection between two co-occurring clusters. */
export interface DeflectionEvent extends EventBase {
  type: "deflection";
  id: string;
  clusterA: ClusterId;
  clusterB: ClusterId;
  level: DeflectionLevel;
  unitA: string;
  unitB: string;
  point: string;
  confidence: ConfidenceTier;
}

/** A streamed chunk of the consolidated answer. */
export interface AnswerChunkEvent extends EventBase {
  type: "answer_chunk";
  segment: AnswerSegment;
}

/** One external web source gathered by the research stage. */
export interface ResearchDocumentEvent extends EventBase {
  type: "research_document";
  document: ResearchDocument;
}

/** Terminal success event. */
export interface DoneEvent extends EventBase {
  type: "done";
  counts: CollectionCounts;
}

/** Terminal error event (also used for transport-level failures). */
export interface StreamErrorEvent extends EventBase {
  type: "error";
  message: string;
  /** True if the client may retry/reconnect. */
  recoverable?: boolean;
}

/** The full discriminated union the stream yields. */
export type WorldviewEvent =
  | QueryStartedEvent
  | StatusEvent
  | DistrictResolvedEvent
  | ClusterDefinedEvent
  | DeflectionEvent
  | AnswerChunkEvent
  | ResearchDocumentEvent
  | DoneEvent
  | StreamErrorEvent;

export type WorldviewEventType = WorldviewEvent["type"];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Build the canonical {@link DistrictId} from a state code + census district
 * code. Used by both the GeoJSON loader and the stream so ids always match.
 */
export function makeDistrictId(stateCode: StateCode, districtCode: string): DistrictId {
  return `${stateCode}-${districtCode}`;
}

/**
 * extrahigh mode only: parse the state code out of a state-scoped cluster id
 * (backend scheme: `f"{state_code}:c{i}"`, e.g. `"27:c0"`, or `"UNK:c0"` for
 * posts geography couldn't resolve). Returns null for basic/medium/high's
 * unscoped ids (`"c0"`, no colon) or the "UNK" sentinel (not a real state).
 * Fallback path only — prefer an explicit `stateCode` field on the event when
 * one is present (see {@link resolveClusterStateCode}).
 */
export function parseStateScopedClusterId(id: ClusterId): StateCode | null {
  const sepIndex = id.indexOf(":");
  if (sepIndex <= 0) return null;
  const stateCode = id.slice(0, sepIndex);
  return stateCode === "UNK" ? null : stateCode;
}

/**
 * Resolve a cluster's state code: prefer an explicit field carried on the
 * event (authoritative, no parsing needed), falling back to parsing it out of
 * the id's own scoping convention for events that don't carry one yet.
 */
export function resolveClusterStateCode(
  explicit: StateCode | undefined,
  id: ClusterId,
): StateCode | undefined {
  return explicit ?? parseStateScopedClusterId(id) ?? undefined;
}
