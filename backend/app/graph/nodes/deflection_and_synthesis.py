"""
Final two pipeline stages: extract points of deflection between co-occurring
viewpoint clusters, then synthesize a consolidated, segment-streamed answer.

Both nodes run after `resolve_district` has populated `state["resolved"]`
(district_id -> ResolvedDistrictState, including per-cluster volumes) and
`state["clusters"]` already holds every ClusterState produced by clustering.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
from functools import lru_cache

from ...config import DATA_DIR
from ...connectors.base import LLMClient
from ...reasoning_modes import EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP
from ...schema import (
    AnswerChunkEvent,
    AnswerSegment,
    CollectionCounts,
    DeflectionEvent,
    StatusEvent,
)
from ..state import DeflectionState, EmitFn, PipelineState, ResolvedDistrictState

_GAZETTEER_PATH = os.path.join(DATA_DIR, "district_gazetteer.json")


@lru_cache(maxsize=1)
def _district_info_by_id() -> dict[str, dict]:
    """district_id -> {"stateCode", "stateName", "districtName"}, deduped from
    the gazetteer (which is keyed by lowercase place name, so many keys map to
    the same district entry). Cached process-wide; the gazetteer is static.
    """
    try:
        with open(_GAZETTEER_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:  # noqa: BLE001 - defensive, purely cosmetic lookup
        print(f"[deflection_and_synthesis] could not load district gazetteer ({exc})")
        return {}

    info: dict[str, dict] = {}
    for entries in raw.values():
        for entry in entries:
            district_id = entry.get("districtId")
            if district_id and district_id not in info:
                info[district_id] = entry
    return info


def _unit_label(rd: ResolvedDistrictState | None) -> str:
    """Human-readable label for a deflection's unitA/unitB: prefer the state
    name from the gazetteer, fall back to the raw state_code, then district_id.
    """
    if rd is None:
        return "unknown"
    info = _district_info_by_id().get(rd["district_id"])
    if info and info.get("stateName"):
        return info["stateName"]
    return rd.get("state_code") or rd.get("district_id") or "unknown"


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


def _total_volume_by_cluster(resolved: dict[str, ResolvedDistrictState]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for rd in resolved.values():
        for cid, vol in rd.get("cluster_volumes", {}).items():
            totals[cid] = totals.get(cid, 0) + vol
    return totals


def _highest_volume_district(
    resolved: dict[str, ResolvedDistrictState], cluster_id: str
) -> ResolvedDistrictState | None:
    """The single district where `cluster_id` has the most accumulated volume
    (not necessarily a district where it's the *dominant* cluster).
    """
    best: ResolvedDistrictState | None = None
    best_vol = -1
    for rd in resolved.values():
        vol = rd.get("cluster_volumes", {}).get(cluster_id, 0)
        if vol > best_vol:
            best_vol = vol
            best = rd
    return best


def _counts_from_state(state: PipelineState) -> CollectionCounts:
    return CollectionCounts(
        posts_collected=state.get("posts_collected", 0),
        districts_resolved=state.get("districts_resolved", 0),
        clusters_found=state.get("clusters_found", 0),
        deflections_found=state.get("deflections_found", 0),
    )


async def extract_deflections(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """Find genuinely co-occurring, distinct dominant viewpoints and extract
    the point of deflection between each pair (capped to the top 6 by
    combined volume), emitting one DeflectionEvent + one StatusEvent per pair.
    """
    resolved = state.get("resolved", {})
    clusters = state.get("clusters", {})

    dominant_ids = sorted(
        {rd["dominant_cluster_id"] for rd in resolved.values() if rd.get("dominant_cluster_id")}
    )

    totals = _total_volume_by_cluster(resolved)
    pairs = list(itertools.combinations(dominant_ids, 2))
    pairs.sort(key=lambda p: totals.get(p[0], 0) + totals.get(p[1], 0), reverse=True)
    pairs = pairs[:6]
    n_pairs = len(pairs)

    for i, (cluster_a_id, cluster_b_id) in enumerate(pairs):
        label_a = _cluster_label(clusters, cluster_a_id)
        label_b = _cluster_label(clusters, cluster_b_id)
        texts_a = _cluster_texts(clusters, cluster_a_id)
        texts_b = _cluster_texts(clusters, cluster_b_id)

        point, confidence = await llm.extract_deflection(label_a, texts_a, label_b, texts_b)

        rd_a = _highest_volume_district(resolved, cluster_a_id)
        rd_b = _highest_volume_district(resolved, cluster_b_id)
        state_code_a = rd_a.get("state_code") if rd_a else None
        state_code_b = rd_b.get("state_code") if rd_b else None
        level = "intra-state" if state_code_a and state_code_a == state_code_b else "inter-state"
        unit_a = _unit_label(rd_a)
        unit_b = _unit_label(rd_b)

        deflection_id = f"def-{cluster_a_id}-{cluster_b_id}"

        await emit(
            DeflectionEvent(
                query_run_id=state["query_run_id"],
                id=deflection_id,
                cluster_a=cluster_a_id,
                cluster_b=cluster_b_id,
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
                cluster_a=cluster_a_id,
                cluster_b=cluster_b_id,
                level=level,
                unit_a=unit_a,
                unit_b=unit_b,
                point=point,
                confidence=confidence,
            )
        )
        state["deflections_found"] = len(state["deflections"])

        progress = 0.55 + 0.15 * ((i + 1) / n_pairs) if n_pairs else 0.7
        found = state["deflections_found"]
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Analyzing deflections… {found} point{'s' if found != 1 else ''} of deflection found",
                phase="deflecting",
                counts=_counts_from_state(state),
                progress=progress,
            )
        )

    if n_pairs == 0:
        # No two districts disagreed on their dominant viewpoint — still
        # report the phase transition so the frontend ticker/progress advance.
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker="Analyzing deflections… 0 points of deflection found",
                phase="deflecting",
                counts=_counts_from_state(state),
                progress=0.7,
            )
        )

    state["phase"] = "deflecting"
    return state


# Mirrors the naming/style of cluster_viewpoints.py's
# _MAX_CONCURRENT_STATE_CLUSTERING: bounds how many states extract deflections
# concurrently, not how much LLM work each one does.
_MAX_CONCURRENT_STATE_DEFLECTION = 6


async def extract_deflections_per_state(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode counterpart to `extract_deflections`: pairs are grouped
    and capped PER STATE (`EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP` each) instead
    of one flat top-6-by-combined-volume cap across all of India -- at the
    per-state cluster scale (dozens to ~190 total clusters), a single global
    cap would let a few high-volume states monopolize every slot, leaving
    most states with zero surfaced deflections. Reuses every pure helper
    (`_cluster_label`, `_cluster_texts`, `_total_volume_by_cluster`,
    `_highest_volume_district`) completely unchanged.

    Because every pair here is drawn from the SAME state's own dominant
    cluster ids by construction, `level` will always land on "intra-state" --
    that's the existing computation below doing exactly what it always did,
    just naturally landing on one outcome given how the inputs are now
    grouped; no new branch is needed to enforce it."""
    resolved = state.get("resolved", {})
    clusters = state.get("clusters", {})
    totals = _total_volume_by_cluster(resolved)

    dominant_by_state: dict[str, set[str]] = {}
    for rd in resolved.values():
        cluster_id = rd.get("dominant_cluster_id")
        if not cluster_id:
            continue
        dominant_by_state.setdefault(rd["state_code"], set()).add(cluster_id)

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_STATE_DEFLECTION)

    async def _deflect_one_state(state_code: str, cluster_ids: set[str]) -> None:
        pairs = list(itertools.combinations(sorted(cluster_ids), 2))
        pairs.sort(key=lambda p: totals.get(p[0], 0) + totals.get(p[1], 0), reverse=True)
        pairs = pairs[:EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP]

        async with semaphore:
            for cluster_a_id, cluster_b_id in pairs:
                label_a = _cluster_label(clusters, cluster_a_id)
                label_b = _cluster_label(clusters, cluster_b_id)
                texts_a = _cluster_texts(clusters, cluster_a_id)
                texts_b = _cluster_texts(clusters, cluster_b_id)

                point, confidence = await llm.extract_deflection(label_a, texts_a, label_b, texts_b)

                rd_a = _highest_volume_district(resolved, cluster_a_id)
                rd_b = _highest_volume_district(resolved, cluster_b_id)
                state_code_a = rd_a.get("state_code") if rd_a else None
                state_code_b = rd_b.get("state_code") if rd_b else None
                level = "intra-state" if state_code_a and state_code_a == state_code_b else "inter-state"
                unit_a = _unit_label(rd_a)
                unit_b = _unit_label(rd_b)

                deflection_id = f"def-{state_code}-{cluster_a_id}-{cluster_b_id}"

                await emit(
                    DeflectionEvent(
                        query_run_id=state["query_run_id"],
                        id=deflection_id,
                        cluster_a=cluster_a_id,
                        cluster_b=cluster_b_id,
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
                        cluster_a=cluster_a_id,
                        cluster_b=cluster_b_id,
                        level=level,
                        unit_a=unit_a,
                        unit_b=unit_b,
                        point=point,
                        confidence=confidence,
                    )
                )
                state["deflections_found"] = len(state["deflections"])

    state_tasks = [
        asyncio.ensure_future(_deflect_one_state(state_code, cluster_ids))
        for state_code, cluster_ids in dominant_by_state.items()
        if len(cluster_ids) >= 2
    ]
    for finished in asyncio.as_completed(state_tasks):
        await finished

    state["phase"] = "deflecting"
    # One trailing summary instead of one StatusEvent per pair (today's
    # per-pair cadence) -- at up to ~64 pairs (32 states x
    # EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP), one-event-per-pair would spam the
    # SSE stream with low-information updates.
    found = state["deflections_found"]
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Analyzing deflections… {found} point{'s' if found != 1 else ''} of deflection "
                f"found across {len(dominant_by_state)} states"
            ),
            phase="deflecting",
            counts=_counts_from_state(state),
            progress=0.9,
        )
    )
    return state


async def synthesize_answer(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """Ask the LLM (or stub) for a consolidated answer built from the found
    clusters + deflections, then stream it out segment-by-segment.
    """
    clusters = state.get("clusters", {})
    cluster_ids = state.get("cluster_order") or list(clusters.keys())

    clusters_payload: list[dict] = []
    for cid in cluster_ids:
        cluster = clusters.get(cid)
        if not cluster:
            continue
        clusters_payload.append(
            {
                "id": cluster.get("id", cid),
                "label": cluster.get("label"),
                "summary": cluster.get("summary"),
                "postCount": len(cluster.get("post_ids") or []),
                # None for basic/medium/high (global, unscoped clusters); set
                # for extrahigh so the synthesis prompt can reason about a
                # much larger, state-grouped cluster set instead of a flat
                # wall of entries with no geography of their own.
                "stateCode": cluster.get("state_code"),
            }
        )

    deflections_payload = [dict(d) for d in state.get("deflections", [])]

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker="Synthesizing the consolidated answer…",
            phase="synthesizing",
            counts=_counts_from_state(state),
            progress=0.85,
        )
    )

    segments = await llm.synthesize_answer(
        state["query"],
        state["query_type"],
        clusters_payload,
        deflections_payload,
        state.get("framings") or [],
        state.get("research_findings") or "",
        state.get("research_documents") or [],
        mode=state["mode"],
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

        # Believable trickle for the frontend's streaming-answer UI even
        # though this first-pass synthesis call isn't itself token-streamed.
        await asyncio.sleep(0.05)

    state["phase"] = "complete"
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Done · {state.get('posts_collected', 0)} posts · "
                f"{state.get('districts_resolved', 0)} districts · "
                f"{state.get('clusters_found', 0)} clusters · "
                f"{state.get('deflections_found', 0)} deflections"
            ),
            phase="complete",
            counts=_counts_from_state(state),
            progress=1.0,
        )
    )

    return state
