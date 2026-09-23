"""
Pydantic mirror of the frontend's streaming event schema
(../src/lib/worldview/types.ts). This file is the wire-format contract: every
event this service emits must serialize (via `.model_dump(by_alias=True)`) to
exactly the JSON shapes the frontend's `WorldviewEvent` union expects.

Python attributes are snake_case (idiomatic); the `alias` on each field is the
camelCase name that actually goes over the wire. Always serialize with
`by_alias=True, exclude_none=True` — see `to_sse_data()` on `WorldviewEvent`.

If you change a shape here, change ../src/lib/worldview/types.ts too (and vice
versa) — there is intentionally no code generation between them yet; keep them
in sync by hand and diff against this docstring's source of truth when in doubt.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .reasoning_modes import LlmProvider, ResearchMode

# ── Shared config ─────────────────────────────────────────────────────────────


class Camel(BaseModel):
    """Base: snake_case Python attrs, camelCase wire format."""

    model_config = ConfigDict(populate_by_name=True)


# ── Scalars / enums (mirror types.ts) ─────────────────────────────────────────

QueryType = Literal["descriptive", "policy"]
ConfidenceTier = Literal["high", "medium", "low"]
ResolutionMethod = Literal[
    "city_subreddit",
    "place_ner",
    "script_language",
    "llm_geolocation",
    "state_fallback",
    # No place signal in the post itself, attributed to the region whose
    # targeted search surfaced it (always "low" confidence).
    "search_context",
    "unresolved",
]
DeflectionLevel = Literal[
    "intra-district", "inter-district", "intra-state", "inter-state", "intra-region", "inter-region"
]
RunPhase = Literal[
    "sourcing",
    "researching",
    "resolving",
    "clustering",
    "deflecting",
    "synthesizing",
    "complete",
]
# "tldr"   — a single-sentence takeaway pinned at the top of the answer panel.
# "body"   — a short framing paragraph shown inline.
# "recommendation" — one tight bullet (the scannable middle of the answer).
# "detail" — long-form prose, collapsed behind a "Full analysis" toggle in the
#            UI so the panel stays small by default without losing depth.
AnswerSegmentKind = Literal["tldr", "heading", "body", "recommendation", "detail"]
# "research" -- see graph/nodes/research.py's _posts_from_research_documents:
# a ResearchDocument (NITI Aayog/data.gov.in/PIB/etc.) turned into a RawPost
# so official sources flow through the same geo-resolution + clustering
# pipeline real social posts do, not just the synthesis stage's citations.
Platform = Literal["reddit", "youtube", "research"]

RGBAColor = Annotated[list[int], Field(min_length=3, max_length=4)]


def make_district_id(state_code: str, district_code: str) -> str:
    """Mirrors makeDistrictId() in types.ts — keep the two in lockstep."""
    return f"{state_code}-{district_code}"


# ── Domain data model ─────────────────────────────────────────────────────────


class SamplePost(Camel):
    id: str
    platform: Platform
    paraphrase: str
    cluster_id: Optional[str] = Field(default=None, alias="clusterId")
    url: Optional[str] = None


class CollectionCounts(Camel):
    posts_collected: int = Field(alias="postsCollected")
    districts_resolved: int = Field(alias="districtsResolved")
    clusters_found: int = Field(alias="clustersFound")
    deflections_found: int = Field(alias="deflectionsFound")
    sources_gathered: int = Field(default=0, alias="sourcesGathered")
    # How many Karnataka regions (incl. the statewide bucket) received posts.
    regions_found: int = Field(default=0, alias="regionsFound")


class ResearchDocument(Camel):
    """One external web source pulled by the research stage.

    `id` is 1-based within a run's ordered source list, and is what
    `AnswerSegment.citations` references (so the frontend can render
    numbered [1] [2] chips linking back to the URLs listed here). `snippet`
    is a short excerpt/summary of what this source contributes -- never the
    verbatim page content, both for copyright and length reasons.
    """

    id: int
    url: str
    title: str
    domain: str
    snippet: str


class AnswerSegment(Camel):
    text: str
    cluster_id: Optional[str] = Field(default=None, alias="clusterId")
    region: Optional[str] = None
    # Which persona region's reply this segment belongs to (set by
    # persona_answers.py, never by the LLM). None for the Karnataka-wide overview.
    region_id: Optional[str] = Field(default=None, alias="regionId")
    kind: Optional[AnswerSegmentKind] = None
    citations: Optional[list[int]] = None  # 1-based indices into the run's ResearchDocument list


# ── Streaming events (discriminated union on `type`, mirrors types.ts) ────────


class EventBase(Camel):
    query_run_id: str = Field(alias="queryRunId")
    t: Optional[float] = None


class QueryStartedEvent(EventBase):
    type: Literal["query_started"] = "query_started"
    query: str
    query_type: QueryType = Field(alias="queryType")
    # Basic/medium/high — see reasoning_modes.py. Geographic coverage is always
    # full regardless of mode; mode controls volume/thoroughness of sourcing.
    mode: ResearchMode
    # Which LLM backend actually ran this query — see reasoning_modes.py.
    provider: LlmProvider


class StatusEvent(EventBase):
    type: Literal["status"] = "status"
    ticker: str
    phase: RunPhase
    counts: CollectionCounts
    progress: float


class RegionResolvedEvent(EventBase):
    """Posts resolved into one Karnataka persona region (or the non-persona
    statewide bucket) for one viewpoint cluster. `volume` is incremental --
    the frontend accumulates per (region, cluster)."""

    type: Literal["region_resolved"] = "region_resolved"
    region_id: str = Field(alias="regionId")
    cluster_id: str = Field(alias="clusterId")
    volume: int
    confidence: ConfidenceTier
    method: ResolutionMethod
    sample_posts: Optional[list[SamplePost]] = Field(default=None, alias="samplePosts")


class ClusterDefinedEvent(EventBase):
    type: Literal["cluster_defined"] = "cluster_defined"
    cluster_id: str = Field(alias="clusterId")
    label: str
    color: RGBAColor
    summary: Optional[str] = None
    representative_posts: Optional[list[SamplePost]] = Field(
        default=None, alias="representativePosts"
    )
    state_code: Optional[str] = Field(default=None, alias="stateCode")
    region_id: Optional[str] = Field(default=None, alias="regionId")


class RegionDefinedEvent(EventBase):
    """Emitted once per Karnataka persona region (and the statewide bucket)
    before any cluster references its id."""

    type: Literal["region_defined"] = "region_defined"
    region_id: str = Field(alias="regionId")
    name: str
    justification: str
    district_ids: list[str] = Field(alias="districtIds")
    state_codes: list[str] = Field(alias="stateCodes")
    confidence: ConfidenceTier


class DeflectionEvent(EventBase):
    type: Literal["deflection"] = "deflection"
    id: str
    cluster_a: str = Field(alias="clusterA")
    cluster_b: str = Field(alias="clusterB")
    level: DeflectionLevel
    unit_a: str = Field(alias="unitA")
    unit_b: str = Field(alias="unitB")
    point: str
    confidence: ConfidenceTier


class AnswerChunkEvent(EventBase):
    type: Literal["answer_chunk"] = "answer_chunk"
    segment: AnswerSegment


class ResearchDocumentEvent(EventBase):
    """One external web source gathered by the research stage. Multiple of these
    stream in during the `researching` phase; the frontend collects them into
    an ordered, de-duplicated (by url) `Sources` list at the bottom of the
    consolidated-answer panel."""

    type: Literal["research_document"] = "research_document"
    document: ResearchDocument


class DivergencePointMatch(Camel):
    persona: str
    baseline: str
    similarity: float


class DivergenceRegionEvent(EventBase):
    """Persona vs. no-persona reply for one region: same question, same
    evidence, same prompt -- only the persona is removed. `status` "failed"
    carries only `error`; every metric field is then absent."""

    type: Literal["divergence_region"] = "divergence_region"
    model: LlmProvider
    region_id: str = Field(alias="regionId")
    region_name: str = Field(alias="regionName")
    status: Literal["ok", "failed"]
    error: Optional[str] = None
    persona_version: Optional[str] = Field(default=None, alias="personaVersion")
    persona_reply: Optional[str] = Field(default=None, alias="personaReply")
    baseline_reply: Optional[str] = Field(default=None, alias="baselineReply")
    # Primary indicator: cosine similarity of the two replies' sentence-mean
    # embeddings; divergence = 1 - similarity.
    semantic_similarity: Optional[float] = Field(default=None, alias="semanticSimilarity")
    divergence: Optional[float] = None
    # Same similarity between two independent no-persona samples -- the
    # run-to-run variation a persona effect has to exceed to mean anything.
    noise_floor: Optional[float] = Field(default=None, alias="noiseFloor")
    # Point-level agreement (BERTScore-style F1 of best-match similarities).
    point_alignment: Optional[float] = Field(default=None, alias="pointAlignment")
    persona_points: Optional[list[str]] = Field(default=None, alias="personaPoints")
    baseline_points: Optional[list[str]] = Field(default=None, alias="baselinePoints")
    shared: Optional[list[DivergencePointMatch]] = None
    reframed: Optional[list[DivergencePointMatch]] = None
    persona_only: Optional[list[str]] = Field(default=None, alias="personaOnly")
    baseline_only: Optional[list[str]] = Field(default=None, alias="baselineOnly")


class DivergenceEmbeddingPoint(Camel):
    x: float
    y: float
    region_id: str = Field(alias="regionId")
    condition: Literal["persona", "baseline"]
    text: str


class DivergenceSummaryEvent(EventBase):
    """Cross-region view once every region is measured. `matrix` is cosine
    similarity between whole replies, ordered by `labels`; `points` are the
    t-SNE projection of every extracted point from every reply."""

    type: Literal["divergence_summary"] = "divergence_summary"
    model: LlmProvider
    embedding_model: str = Field(alias="embeddingModel")
    labels: list[dict]
    matrix: list[list[float]]
    # Mean pairwise similarity between the four regions' replies, per condition
    # -- lower means the regions' answers differ more from each other.
    persona_cross_region_similarity: Optional[float] = Field(
        default=None, alias="personaCrossRegionSimilarity"
    )
    baseline_cross_region_similarity: Optional[float] = Field(
        default=None, alias="baselineCrossRegionSimilarity"
    )
    points: list[DivergenceEmbeddingPoint]
    perplexity: Optional[float] = None


class ModelAgreement(Camel):
    region_id: str = Field(alias="regionId")
    model_a: LlmProvider = Field(alias="modelA")
    model_b: LlmProvider = Field(alias="modelB")
    # Similarity between the two models' replies to the same prompt.
    persona: float
    baseline: float
    # Each model's persona-vs-no-persona divergence, side by side.
    divergence_a: float = Field(alias="divergenceA")
    divergence_b: float = Field(alias="divergenceB")


class DivergenceModelsEvent(EventBase):
    """Cross-model view once every model is measured: do two LLMs, given the
    same persona and evidence, say the same thing -- and does the persona move
    each of them by the same amount?"""

    type: Literal["divergence_models"] = "divergence_models"
    models: list[dict]  # [{id, label}] in display order
    agreements: list[ModelAgreement]


class DoneEvent(EventBase):
    type: Literal["done"] = "done"
    counts: CollectionCounts


class StreamErrorEvent(EventBase):
    type: Literal["error"] = "error"
    message: str
    recoverable: Optional[bool] = None


WorldviewEvent = Annotated[
    Union[
        QueryStartedEvent,
        StatusEvent,
        RegionResolvedEvent,
        ClusterDefinedEvent,
        RegionDefinedEvent,
        DeflectionEvent,
        AnswerChunkEvent,
        ResearchDocumentEvent,
        DivergenceRegionEvent,
        DivergenceSummaryEvent,
        DivergenceModelsEvent,
        DoneEvent,
        StreamErrorEvent,
    ],
    Field(discriminator="type"),
]


def event_to_sse_data(event: BaseModel) -> str:
    """JSON string for one SSE `data:` line — camelCase, no null clutter."""
    return event.model_dump_json(by_alias=True, exclude_none=True)
