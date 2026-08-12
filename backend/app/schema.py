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
    "unresolved",
]
DeflectionLevel = Literal[
    "intra-district", "inter-district", "intra-state", "inter-state", "inter-region"
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
Platform = Literal["reddit", "youtube"]

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


class DistrictResolvedEvent(EventBase):
    type: Literal["district_resolved"] = "district_resolved"
    district_id: str = Field(alias="districtId")
    state_code: str = Field(alias="stateCode")
    cluster_id: str = Field(alias="clusterId")
    confidence: ConfidenceTier
    volume: int
    method: ResolutionMethod
    is_state_fallback: Optional[bool] = Field(default=None, alias="isStateFallback")
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
    # extrahigh mode only (None for basic/medium/high, whose clusters are
    # global/unscoped) -- which state this cluster belongs to. Lets the
    # frontend group/color per-state clusters without parsing it out of the
    # cluster id string. excluded from the wire payload entirely when None
    # (Camel serializes with exclude_none), so existing modes' payloads are
    # byte-identical to before this field existed.
    state_code: Optional[str] = Field(default=None, alias="stateCode")


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
        DistrictResolvedEvent,
        ClusterDefinedEvent,
        DeflectionEvent,
        AnswerChunkEvent,
        ResearchDocumentEvent,
        DoneEvent,
        StreamErrorEvent,
    ],
    Field(discriminator="type"),
]


def event_to_sse_data(event: BaseModel) -> str:
    """JSON string for one SSE `data:` line — camelCase, no null clutter."""
    return event.model_dump_json(by_alias=True, exclude_none=True)
