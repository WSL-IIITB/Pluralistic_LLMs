"""
Deflections and the Karnataka-wide synthesis.

`extract_region_deflections` finds the point two co-occurring viewpoints fork
on -- within each persona region (its top clusters) and across regions (each
region's dominant cluster). `synthesize_answer` writes the region-BLIND
Karnataka-wide overview; each region's own reply is written afterwards, in its
persona, by persona_answers.py.
"""

from __future__ import annotations

import asyncio
import itertools

from ...connectors.base import LLMClient
from ...reasoning_modes import EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP
from ...schema import (
    AnswerChunkEvent,
    AnswerSegment,
    CollectionCounts,
    DeflectionEvent,
    StatusEvent,
)
from ..state import DeflectionState, EmitFn, PipelineState


def _cluster_label(clusters: dict, cluster_id: str) -> str:
    cluster = clusters.get(cluster_id)
    if cluster and cluster.get("label"):
        return cluster["label"]
    return cluster_id


def _cluster_texts(clusters: dict, cluster_id: str) -> list[str]:
    """Representative paraphrase texts for a cluster, or a generic fallback
    label if it has no representative posts (still gives the LLM something).
    """
    cluster = clusters.get(cluster_id)
    reps = (cluster.get("representative_posts") or []) if cluster else []
    texts = [p.get("paraphrase") for p in reps if p.get("paraphrase")]
    if texts:
        return texts
    return [_cluster_label(clusters, cluster_id)]


def _counts_from_state(state: PipelineState) -> CollectionCounts:
    return CollectionCounts(
        posts_collected=state.get("posts_collected", 0),
        districts_resolved=state.get("districts_resolved", 0),
        clusters_found=state.get("clusters_found", 0),
        deflections_found=state.get("deflections_found", 0),
        regions_found=len(state.get("regions") or {}),
    )


def _region_label(state: PipelineState, region_id: str | None) -> str:
    if not region_id:
        return "unknown"
    region = state.get("regions", {}).get(region_id)
    if region and region.get("name"):
        return region["name"]
    return region_id


_MAX_CONCURRENT_REGION_DEFLECTION = 6


async def synthesize_answer(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """The Karnataka-wide overview: every region's clusters + deflections +
    research, REGION-BLIND on purpose (cluster payloads carry no region/state
    field) -- the region-specific answers are the persona replies that follow
    (persona_answers.py). Streams its segments without a regionId."""
    clusters = state.get("clusters", {})
    clusters_payload = [
        {
            "id": cluster.get("id", cid),
            "label": cluster.get("label"),
            "summary": cluster.get("summary"),
            "postCount": len(cluster.get("post_ids") or []),
        }
        for cid in state.get("cluster_order") or list(clusters)
        if (cluster := clusters.get(cid))
    ]

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker="Synthesizing the Karnataka-wide overview…",
            phase="synthesizing",
            counts=_counts_from_state(state),
            progress=0.85,
        )
    )

    segments = await llm.synthesize_answer(
        state["query"],
        state["query_type"],
        clusters_payload,
        [dict(d) for d in state.get("deflections", [])],
        state.get("framings") or [],
        state.get("research_findings") or "",
        state.get("research_documents") or [],
        mode="high",
    )

    state["answer_segments"] = []
    for seg in segments or []:
        if not isinstance(seg, dict) or not seg.get("text"):
            continue
        kwargs: dict = {"text": seg["text"]}
        if seg.get("kind") is not None:
            kwargs["kind"] = seg["kind"]
        cluster_id = seg.get("clusterId", seg.get("cluster_id"))
        if cluster_id is not None:
            kwargs["cluster_id"] = cluster_id
        if seg.get("region") is not None:
            kwargs["region"] = seg["region"]
        if isinstance(seg.get("citations"), list) and seg["citations"]:
            kwargs["citations"] = list(seg["citations"])
        segment = AnswerSegment(**kwargs)
        await emit(AnswerChunkEvent(query_run_id=state["query_run_id"], segment=segment))
        state["answer_segments"].append(segment.model_dump(by_alias=True, exclude_none=True))
        # Believable trickle for the streaming-answer UI (the call itself isn't token-streamed).
        await asyncio.sleep(0.05)

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker="Karnataka-wide overview ready · writing each region's persona reply…",
            phase="synthesizing",
            counts=_counts_from_state(state),
            progress=0.88,
        )
    )
    return state


# ── Karnataka persona-region deflections ────────────────────────────────────


async def extract_region_deflections(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """Two passes over state["region_stats"] (aggregate_regions):
      - intra-region: the region's top clusters by volume, pairwise
        (EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP per region);
      - inter-region: each persona region's dominant cluster against every
        other region's (4 regions -> at most 6 pairs)."""
    from ...karnataka import region_by_id

    clusters = state.get("clusters", {})
    stats = state.get("region_stats", {})
    persona_ids = set(region_by_id())
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REGION_DEFLECTION)

    async def _deflect(cluster_a: str, cluster_b: str, level: str, unit_a: str, unit_b: str, deflection_id: str) -> None:
        async with semaphore:
            point, confidence = await llm.extract_deflection(
                _cluster_label(clusters, cluster_a),
                _cluster_texts(clusters, cluster_a),
                _cluster_label(clusters, cluster_b),
                _cluster_texts(clusters, cluster_b),
            )
        await emit(
            DeflectionEvent(
                query_run_id=state["query_run_id"],
                id=deflection_id,
                cluster_a=cluster_a,
                cluster_b=cluster_b,
                level=level,  # type: ignore[arg-type]
                unit_a=unit_a,
                unit_b=unit_b,
                point=point,
                confidence=confidence,  # type: ignore[arg-type]
            )
        )
        state["deflections"].append(
            DeflectionState(
                id=deflection_id,
                cluster_a=cluster_a,
                cluster_b=cluster_b,
                level=level,
                unit_a=unit_a,
                unit_b=unit_b,
                point=point,
                confidence=confidence,
            )
        )
        state["deflections_found"] = len(state["deflections"])

    tasks = []
    for region_id, rs in stats.items():
        name = _region_label(state, region_id)
        top = [cid for cid, _ in sorted(rs["cluster_volumes"].items(), key=lambda kv: kv[1], reverse=True)[:3]]
        pairs = list(itertools.combinations(top, 2))[:EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP]
        for a, b in pairs:
            tasks.append(_deflect(a, b, "intra-region", name, name, f"def-{a}-{b}"))

    dominant = {rid: rs["dominant_cluster_id"] for rid, rs in stats.items() if rid in persona_ids and rs["dominant_cluster_id"]}
    for ra, rb in itertools.combinations(sorted(dominant), 2):
        tasks.append(
            _deflect(
                dominant[ra],
                dominant[rb],
                "inter-region",
                _region_label(state, ra),
                _region_label(state, rb),
                f"def-interregion-{ra}-{rb}",
            )
        )

    await asyncio.gather(*tasks)

    state["phase"] = "deflecting"
    found = state["deflections_found"]
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=f"{found} point{'s' if found != 1 else ''} of deflection found across Karnataka's regions",
            phase="deflecting",
            counts=_counts_from_state(state),
            progress=0.82,
        )
    )
    return state
