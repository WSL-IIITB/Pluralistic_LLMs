"""
LangGraph shared state + the per-run event emitter.

The graph's own state (this file) is deliberately plain TypedDicts — cheap to
copy/merge across nodes. Outbound wire events are always constructed with the
strict Pydantic models in ../schema.py and pushed through `EmitFn`, which is
how a node reports fine-grained progress independently of LangGraph's own
coarse per-node state streaming.
"""

from __future__ import annotations

from typing import Awaitable, Callable, TypedDict

from ..reasoning_modes import ResearchMode
from ..schema import WorldviewEvent


class RawPost(TypedDict):
    id: str
    platform: str  # "reddit" | "youtube" | "research"
    text: str
    # Subreddit name (reddit) or channel/video title (youtube) / source domain (research).
    source_hint: str
    permalink: str | None
    # Set by clustering (cluster_viewpoints_per_region).
    cluster_id: str | None
    # Set by resolve_regions.py (research posts arrive pre-resolved from research.py).
    state_code: str | None
    district_id: str | None
    resolution_method: str | None  # ResolutionMethod
    resolution_confidence: str | None  # ConfidenceTier
    # One of the persona region ids, or the statewide bucket (see karnataka.py).
    region_id: str | None
    # Karnataka persona region whose targeted search surfaced this post (None
    # for statewide/framing searches) -- the weakest geography signal, used
    # only when the post itself names no place (method "search_context").
    source_region_id: str | None


class RegionStatsState(TypedDict):
    """Per-region aggregate the map renders -- one per persona region plus the
    statewide bucket."""

    region_id: str
    cluster_volumes: dict[str, int]
    dominant_cluster_id: str | None
    confidence: str  # ConfidenceTier
    method: str  # ResolutionMethod, most common among the region's posts


class ClusterState(TypedDict):
    id: str
    label: str
    color: list[int]
    summary: str | None
    representative_posts: list[dict]  # SamplePost-shaped dicts
    post_ids: list[str]  # RawPost ids assigned here — feeds deflection/synthesis
    state_code: str | None
    region_id: str | None


class RegionState(TypedDict):
    """A Karnataka persona region (or the statewide bucket), fixed per run --
    see karnataka.py. `justification` carries the persona's region definition."""

    id: str
    name: str
    justification: str
    district_ids: list[str]
    state_codes: list[str]
    confidence: str  # ConfidenceTier
    worldview_text: str


class DeflectionState(TypedDict):
    id: str
    cluster_a: str
    cluster_b: str
    level: str  # DeflectionLevel
    unit_a: str
    unit_b: str
    point: str
    confidence: str  # ConfidenceTier


class PipelineState(TypedDict):
    query_run_id: str
    query: str
    query_type: str  # QueryType — set by an early classification step
    mode: ResearchMode
    provider: str  # LlmProvider that runs the main pipeline
    phase: str  # RunPhase

    posts: list[RawPost]
    clusters: dict[str, ClusterState]  # keyed by cluster_id
    cluster_order: list[str]
    # region_id -> RawPost ids placed in that region (resolve_regions.py).
    posts_by_region: dict[str, list[str]]
    regions: dict[str, RegionState]  # keyed by region_id
    deflections: list[DeflectionState]
    region_stats: dict[str, RegionStatsState]
    # Per persona region: the exact evidence handed to its reply, kept so the
    # no-persona reply in the divergence stage gets byte-identical inputs.
    region_evidence: dict[str, dict]
    # Per persona region: {"segments": [...], "text": str} of the persona reply.
    region_replies: dict[str, dict]
    answer_segments: list[dict]  # AnswerSegment-shaped dicts
    # Karnataka-scoped framings of the topic (llm.suggest_framings) -- steer
    # sourcing and ground the overview synthesis.
    framings: list[str]

    # Web-search-grounded external sources from the research stage:
    #   research_findings: concatenated LLM-written summary of what search surfaced.
    #   research_documents: 1-based-ordered, url-deduped {id, url, title, domain,
    #                       snippet, source_region_id} -- streamed as
    #                       ResearchDocumentEvents and cited by answer segments.
    research_findings: str
    research_documents: list[dict]

    posts_collected: int
    districts_resolved: int
    clusters_found: int
    deflections_found: int


def new_pipeline_state(query_run_id: str, query: str, mode: ResearchMode, provider: str) -> PipelineState:
    return PipelineState(
        query_run_id=query_run_id,
        query=query,
        query_type="descriptive",
        mode=mode,
        provider=provider,
        phase="sourcing",
        posts=[],
        clusters={},
        cluster_order=[],
        posts_by_region={},
        regions={},
        deflections=[],
        region_stats={},
        region_evidence={},
        region_replies={},
        answer_segments=[],
        framings=[],
        research_findings="",
        research_documents=[],
        posts_collected=0,
        districts_resolved=0,
        clusters_found=0,
        deflections_found=0,
    )


EmitFn = Callable[[WorldviewEvent], Awaitable[None]]
"""Passed into every node so it can push granular progress events as it works.
Construct events with the Pydantic classes in ../schema.py — the gateway only
serializes (`event_to_sse_data`) and forwards whatever comes through."""
