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
    platform: str  # "reddit" | "youtube" | "niti" (raw CSV connector output is SourcedPost; RawPost is the stage's own copy)
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
    # extrahigh mode only (None until infer_regions.py runs): which
    # agent-inferred region this post's district was grouped into. Set by
    # infer_regions.py, once per post, for every post whose district_id ended
    # up in some region (i.e. every post with a resolved district_id, by that
    # module's own coverage invariant).
    region_id: str | None


class ResolvedDistrictState(TypedDict):
    district_id: str
    state_code: str
    cluster_volumes: dict[str, int]  # clusterId -> accumulated post volume
    dominant_cluster_id: str
    method: str  # ResolutionMethod
    confidence: str  # ConfidenceTier
    is_state_fallback: bool
    sample_posts: list[dict]  # SamplePost-shaped dicts (paraphrased only)
    # extrahigh mode only (None for basic/medium/high, and for extrahigh runs
    # predating region-inference) -- fixed once at creation (unlike
    # confidence/method/is_state_fallback above, a district belongs to
    # exactly one region for the whole run, so there's no dominant-cluster
    # nuance to apply here).
    region_id: str | None


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
    #
    # For region-mode clusters (cluster_viewpoints_per_region), this is a
    # REPRESENTATIVE state (the region's highest-post-volume district's
    # state), not the cluster's one true state -- a region-mode cluster can
    # genuinely span multiple states. Transitional backward-compat shim so
    # existing state-keyed frontend grouping/coloring doesn't silently break
    # before the region-aware frontend work lands; region_id below is the
    # new authoritative field for region-mode clusters.
    state_code: str | None
    region_id: str | None


class RegionState(TypedDict):
    """extrahigh mode only -- an agent-inferred region (see
    graph/nodes/infer_regions.py), NOT a fixed administrative unit. Can span
    several districts and cross multiple state boundaries; `district_ids`/
    `state_codes` are derived from the numeric partition + LLM naming that
    module produces. `worldview_text` starts empty and is filled in by the
    two-pass synthesis stage (condition_answer_for_region) once that lands --
    it's the region's inferred worldview/priorities digest, persisted to the
    region knowledge base for reuse by future queries."""

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
    # extrahigh mode only (stays empty until infer_regions.py runs): region_id
    # -> RawPost ids belonging to that region, populated by
    # graph/nodes/infer_regions.py. Not yet consumed by clustering (that's a
    # later phase's job) -- coexists with posts_by_state above rather than
    # replacing it while that wiring lands incrementally.
    posts_by_region: dict[str, list[str]]
    regions: dict[str, RegionState]  # keyed by region_id
    # Set once by infer_regions.py's single llm.embed() call over every post's
    # text (index-aligned with state["posts"]) so a later per-region
    # clustering stage can reuse it instead of re-embedding the same corpus.
    # None until infer_regions.py runs.
    post_embeddings: list[list[float]] | None
    deflections: list[DeflectionState]
    answer_segments: list[dict]  # AnswerSegment-shaped dicts
    # A stable, write-once snapshot of `answer_segments` taken right after
    # `synthesize_answer` (pass 1, the region-BLIND national baseline)
    # populates it -- both `condition_regions` (pass 2) and `condition_states`
    # (pass 3) read baseline segments from HERE, never from the ever-growing
    # `answer_segments` above, since by the time pass 3 runs, `answer_segments`
    # already holds pass 1 AND pass 2's output too. Empty for basic/medium/high
    # (they never run the conditioning passes that would read it).
    baseline_answer_segments: list[dict]
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
        posts_by_region={},
        regions={},
        post_embeddings=None,
        deflections=[],
        answer_segments=[],
        baseline_answer_segments=[],
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
