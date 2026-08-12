"""
LangGraph shared state + the per-run event emitter.

The graph's own state (this file) is deliberately plain TypedDicts — cheap to
copy/merge across nodes. Outbound wire events are always constructed with the
strict Pydantic models in ../schema.py and pushed through `EmitFn`, which is
how a node reports fine-grained progress (e.g. one `district_resolved` per
batch) independently of LangGraph's own coarse per-node state streaming.
"""

from __future__ import annotations

from typing import Awaitable, Callable, TypedDict

from ..reasoning_modes import ResearchMode
from ..schema import WorldviewEvent


class RawPost(TypedDict):
    id: str
    platform: str  # "reddit" | "youtube"
    text: str
    # Subreddit name (reddit) or channel/video title (youtube) — the strongest
    # single signal the district resolver has before falling back to NER/LLM.
    source_hint: str
    permalink: str | None
    # Set by the cluster_viewpoints node. `district_resolved` events require a
    # clusterId, so clustering runs BEFORE district resolution in this graph
    # (source -> cluster -> resolve_district -> deflection -> synthesize) —
    # resolve_district only aggregates volume per (district, cluster) once
    # every post already carries one.
    cluster_id: str | None
    # extrahigh mode only (None for basic/medium/high): set by
    # geo_resolve.py's resolve_posts_geography, which runs geography
    # resolution BEFORE clustering so posts can be grouped per-state prior to
    # cluster_viewpoints_per_state. Mirrors exactly what _resolve_post already
    # returns; resolve_district.py's finalize_districts reads these back
    # (alongside the now-set cluster_id) to call the existing _apply_resolution
    # unchanged, once per post.
    state_code: str | None
    district_id: str | None
    resolution_method: str | None  # ResolutionMethod
    resolution_confidence: str | None  # ConfidenceTier


class ResolvedDistrictState(TypedDict):
    district_id: str
    state_code: str
    cluster_volumes: dict[str, int]  # clusterId -> accumulated post volume
    dominant_cluster_id: str
    method: str  # ResolutionMethod
    confidence: str  # ConfidenceTier
    is_state_fallback: bool
    sample_posts: list[dict]  # SamplePost-shaped dicts (paraphrased only)


class ClusterState(TypedDict):
    id: str
    label: str
    color: list[int]
    summary: str | None
    representative_posts: list[dict]  # SamplePost-shaped dicts
    post_ids: list[str]  # RawPost ids assigned here — feeds deflection/synthesis
    # extrahigh mode only (None for basic/medium/high, whose clusters are
    # global/unscoped): which state this cluster belongs to. Set by
    # cluster_viewpoints_per_state; the cluster's own id already embeds this
    # (f"{state_code}:c{i}") but this field avoids parsing it back out.
    state_code: str | None


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
    phase: str  # RunPhase

    posts: list[RawPost]
    resolved: dict[str, ResolvedDistrictState]  # keyed by district_id
    clusters: dict[str, ClusterState]  # keyed by cluster_id
    cluster_order: list[str]
    # extrahigh mode only (stays empty for basic/medium/high): state_code ->
    # RawPost ids geo-resolved into that state, populated by geo_resolve.py's
    # resolve_posts_geography before cluster_viewpoints_per_state runs.
    # Geography-unresolvable posts bucket under the "UNK" sentinel key so
    # nothing is silently dropped from clustering.
    posts_by_state: dict[str, list[str]]
    deflections: list[DeflectionState]
    answer_segments: list[dict]  # AnswerSegment-shaped dicts
    # Well-known regional/cultural framings suggested up front (see
    # llm.suggest_framings), used both to steer sourcing toward substantive
    # content and to ground the final synthesis in real-world knowledge
    # instead of only whatever noisy phrasing the scraped posts happened to use.
    framings: list[str]

    # Web-search-grounded external sources from the research stage. Two shapes:
    #   research_findings: concatenated LLM-written summary of what the web
    #                       search surfaced, ready to hand to synthesis.
    #   research_documents: 1-based-ordered dedup list of source dicts:
    #                       {id, url, title, domain, snippet}. These stream to
    #                       the frontend as ResearchDocumentEvents and land in
    #                       the "Sources" section of the consolidated answer.
    research_findings: str
    research_documents: list[dict]

    posts_collected: int
    districts_resolved: int
    clusters_found: int
    deflections_found: int


def new_pipeline_state(query_run_id: str, query: str, mode: ResearchMode) -> PipelineState:
    return PipelineState(
        query_run_id=query_run_id,
        query=query,
        query_type="descriptive",
        mode=mode,
        phase="sourcing",
        posts=[],
        resolved={},
        clusters={},
        cluster_order=[],
        posts_by_state={},
        deflections=[],
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
