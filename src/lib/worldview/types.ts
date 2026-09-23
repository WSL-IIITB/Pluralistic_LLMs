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

/**
 * Agent-inferred region identifier (extrahigh mode only), e.g. `"r3"`, or the
 * `"UNK-REGION"` sentinel for geography-unresolvable posts. Unlike
 * {@link StateCode}, a region is NOT a fixed administrative unit — it can
 * span several districts and cross multiple state boundaries, and its exact
 * membership/name is inferred fresh per run (see {@link RegionDatum}).
 */
export type RegionId = string;

/** deck.gl RGB(A) colour, channels 0–255. Alpha optional (defaults opaque). */
export type RGBAColor = [number, number, number] | [number, number, number, number];

/** Whether the answer is a neutral description or a policy recommendation. */
export type QueryType = "descriptive" | "policy";

/**
 * How thorough a run is. Geographic coverage is always full regardless of
 * mode (every Indian state gets surveyed) — for basic/medium/high, mode
 * instead controls the VOLUME of sources gathered per state/framing and how
 * much effort the research stage spends per angle. "extrahigh" is
 * qualitatively different, not just "more of the same": the backend infers
 * AGENT-DEFINED REGIONS from the data (each can span several districts and
 * cross multiple state boundaries — see {@link RegionDatum}) and clusters
 * each region's posts independently instead of pooling everything into one
 * global clustering pass, so a single run can produce dozens of distinct
 * viewpoint clusters instead of today's 2-6, each traceable to the specific
 * region it came from. Mirrors the backend's `reasoning_modes.ResearchMode`.
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
 * pipeline (region-inference + per-region clustering, ~3x the LLM call volume, see ResearchMode's
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
 * Which LLM backend answers a run. "azure_anthropic" is Claude via Azure AI
 * Foundry — removed at one point and since restored, so it is selectable
 * again (but not the default). "openai" is selectable in the type but the UI
 * keeps it disabled (that account is out of credits);
 * "gemma_local"/"mistral_local" run entirely on-device via Ollama, zero
 * per-call cost; "gemma_remote" is a self-hosted, OpenAI-compatible Gemma
 * server needing no credential, and is the DEFAULT.
 * Mirrors the backend's `reasoning_modes.LlmProvider`.
 */
export type LlmProvider =
  "azure_anthropic" | "openai" | "gemma_local" | "mistral_local" | "gemma_remote";

export const LLM_PROVIDERS: readonly LlmProvider[] = [
  "azure_anthropic",
  "openai",
  "gemma_local",
  "mistral_local",
  "gemma_remote",
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
  /** No place in the post itself; attributed to the region whose targeted search found it. */
  | "search_context"
  | "unresolved";

/** The two viewpoints in a deflection can co-occur at different scales. */
export type DeflectionLevel =
  | "intra-district"
  | "inter-district"
  | "intra-state"
  | "inter-state"
  | "intra-region"
  | "inter-region";

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
  /** "research" — an official/statistical source (NITI Aayog, data.gov.in,
   *  PIB, etc.) turned into a post-like entry so it can be geo-resolved and
   *  clustered alongside real social posts — see the backend's
   *  research.py module docstring. */
  platform: "reddit" | "youtube" | "research";
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
   *
   * Region-mode transitional value: for a region-scoped cluster (regionId
   * set below), this is a REPRESENTATIVE state (the region's highest-volume
   * district's state), not the cluster's one true state — a region-mode
   * cluster can genuinely span multiple states. Still useful for the
   * district card's own state label; {@link regionId} is the authoritative
   * grouping key for region-mode clusters.
   */
  stateCode?: StateCode;
  /** extrahigh mode only (undefined for basic/medium/high, and for older
   *  saved runs predating region-inference) — which agent-inferred region
   *  this cluster belongs to. See {@link RegionDatum} for the region's name/
   *  membership, delivered separately via a `region_defined` event. */
  regionId?: RegionId;
}

/**
 * An agent-inferred region (extrahigh mode only) — see {@link RegionId}.
 * Delivered once per region via `region_defined`, before any cluster/
 * district event references its id.
 */
export interface RegionDatum {
  id: RegionId;
  name: string;
  /** One-sentence rationale for why these districts were grouped together. */
  justification: string;
  districtIds: DistrictId[];
  stateCodes: StateCode[];
  confidence: ConfidenceTier;
}

/** One Karnataka persona region's (or the statewide bucket's) accumulated reading. */
export interface RegionStatsDatum {
  regionId: RegionId;
  /** Dominant cluster (argmax of clusterVolumes). */
  clusterId: ClusterId | null;
  clusterVolumes: Record<ClusterId, number>;
  volume: number;
  confidence: ConfidenceTier;
  method: ResolutionMethod;
  samplePosts: SamplePost[];
}

export interface DivergencePointMatch {
  persona: string;
  baseline: string;
  similarity: number;
}

/** Persona vs. no-persona reply for one region (same question, same evidence). */
export interface DivergenceRegion {
  regionId: RegionId;
  regionName: string;
  status: "ok" | "failed";
  error?: string;
  personaVersion?: string;
  personaReply?: string;
  baselineReply?: string;
  /** Primary indicator: cosine similarity of the two replies (0–1, higher = more alike). */
  semanticSimilarity?: number;
  divergence?: number;
  /** Similarity between two independent no-persona samples — sampling noise. */
  noiseFloor?: number;
  pointAlignment?: number;
  personaPoints?: string[];
  baselinePoints?: string[];
  shared?: DivergencePointMatch[];
  reframed?: DivergencePointMatch[];
  personaOnly?: string[];
  baselineOnly?: string[];
}

export type DivergenceCondition = "persona" | "baseline";

export interface DivergenceEmbeddingPoint {
  x: number;
  y: number;
  regionId: RegionId;
  condition: DivergenceCondition;
  text: string;
}

export interface DivergenceSummary {
  embeddingModel: string;
  labels: { regionId: RegionId; regionName: string; condition: DivergenceCondition }[];
  matrix: number[][];
  personaCrossRegionSimilarity?: number;
  baselineCrossRegionSimilarity?: number;
  points: DivergenceEmbeddingPoint[];
  perplexity?: number;
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
  /** Region label shown with the segment. */
  region?: string;
  /** Which persona region's reply this segment belongs to (set by the backend,
   *  never by the LLM). Undefined for the Karnataka-wide overview. */
  regionId?: RegionId;
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
  /** extrahigh mode only (0 for basic/medium/high) — how many agent-inferred
   *  regions this run produced. */
  regionsFound: number;
}

/**
 * Lightweight list-view entry for a saved run — everything needed to render
 * one row in the History panel without fetching the full run (districts/
 * clusters/answer, which can be large, especially for extrahigh mode). The
 * full payload for a given `id` is fetched separately, on demand, via
 * `fetchSavedRun` — see {@link SavedRunData} in store.ts for that shape.
 */
export interface SavedRunSummary {
  id: QueryRunId;
  query: string;
  queryType: QueryType;
  mode: ResearchMode;
  provider: LlmProvider;
  /** ISO timestamp, stamped server-side at save time. */
  createdAt: string;
  /** Regions for Karnataka runs; districts for legacy India-wide runs (see `scope`). */
  areasCount: number;
  clustersCount: number;
  deflectionsCount: number;
  scope: "karnataka-regions" | "india-districts";
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

/** Posts resolved into a Karnataka region for one cluster (incremental volume). */
export interface RegionResolvedEvent extends EventBase {
  type: "region_resolved";
  regionId: RegionId;
  clusterId: ClusterId;
  volume: number;
  confidence: ConfidenceTier;
  method: ResolutionMethod;
  samplePosts?: SamplePost[];
}

export interface DivergenceRegionEvent extends EventBase, DivergenceRegion {
  type: "divergence_region";
}

export interface DivergenceSummaryEvent extends EventBase, DivergenceSummary {
  type: "divergence_summary";
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
  /** extrahigh mode only — see {@link ClusterDatum.regionId}. */
  regionId?: RegionId;
}

/** An agent-inferred region was defined — see {@link RegionDatum}. Emitted
 *  once per region, before any cluster/district event references its id. */
export interface RegionDefinedEvent extends EventBase {
  type: "region_defined";
  regionId: RegionId;
  name: string;
  justification: string;
  districtIds: DistrictId[];
  stateCodes: StateCode[];
  confidence: ConfidenceTier;
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
  | RegionResolvedEvent
  | ClusterDefinedEvent
  | RegionDefinedEvent
  | DeflectionEvent
  | AnswerChunkEvent
  | ResearchDocumentEvent
  | DivergenceRegionEvent
  | DivergenceSummaryEvent
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
