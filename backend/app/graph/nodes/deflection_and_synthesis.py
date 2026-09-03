"""
Final pipeline stages: extract points of deflection between co-occurring
viewpoint clusters, then synthesize a consolidated, segment-streamed answer.

Every node here runs after `resolve_district` has populated `state["resolved"]`
(district_id -> ResolvedDistrictState, including per-cluster volumes) and
`state["clusters"]` already holds every ClusterState produced by clustering.

extrahigh mode's synthesis is THREE-PASS, split across three nodes:
  - `synthesize_answer` (pass 1): produces a region-BLIND national baseline
    answer -- clusters_payload has state/region fields stripped and `mode`
    is downgraded to a non-extrahigh value, reusing the existing, already-
    tuned non-extrahigh prompt path instead of a third near-duplicate one.
    Snapshots its output to `state["baseline_answer_segments"]` once --
    passes 2 and 3 both read baseline segments from THAT stable snapshot,
    never from the ever-growing `state["answer_segments"]`, which by pass 3
    also holds pass 2's own output.
  - `condition_regions` (pass 2, extrahigh-only, runs directly after): fans
    out one call per region asking how THAT region's actual clusters/
    deflections differ from the baseline, conditioned on region_kb.py's
    persistent knowledge base when a relevant past worldview digest exists,
    and persists its own output there for future runs.
  - `condition_states` (pass 3, extrahigh-only, runs directly after pass 2):
    fans out one call per ADMINISTRATIVE STATE (not agent-inferred region)
    asking how THAT state's actual research/social-media discourse differs
    from the baseline, deliberately keeping the two source types (mainstream/
    official research documents vs. social-media viewpoint clusters)
    EXPLICITLY SEPARATE in the produced segments rather than blended into one
    paragraph -- see `_state_clusters_payload`/`_state_deflections_payload`
    and `connectors/base.py`'s `condition_answer_for_state`. Owns the run's
    true completion event in extrahigh mode, as the new true last node --
    `synthesize_answer` deliberately skips it when region-mode is active, and
    `condition_regions` no longer owns it either now that this runs after it.
basic/medium/high never run `condition_regions`/`condition_states` (see
graph/build.py's topology) -- `synthesize_answer` alone remains the complete,
one-pass answer for those modes, unchanged from before this split existed.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
from functools import lru_cache

from ...config import DATA_DIR
from ...connectors.base import LLMClient
from ...reasoning_modes import (
    EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP,
    EXTRAHIGH_DEFLECTIONS_PER_STATE_CAP,
    EXTRAHIGH_INTER_REGION_DEFLECTIONS_CAP,
)
from ...region_kb import get_region_conditioning, persist_region_snapshot
from ...schema import (
    AnswerChunkEvent,
    AnswerSegment,
    CollectionCounts,
    DeflectionEvent,
    StatusEvent,
)
from ..state import DeflectionState, EmitFn, PipelineState, RegionState, ResolvedDistrictState

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
        regions_found=len(state.get("regions") or {}),
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


def _region_label(state: PipelineState, region_id: str | None) -> str:
    if not region_id:
        return "unknown"
    region = state.get("regions", {}).get(region_id)
    if region and region.get("name"):
        return region["name"]
    return region_id


# Mirrors _MAX_CONCURRENT_STATE_DEFLECTION's naming/style: bounds how many
# regions extract intra-region deflections concurrently, not how much LLM
# work each one does.
_MAX_CONCURRENT_REGION_DEFLECTION = 6


async def extract_deflections_per_region(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode counterpart to `extract_deflections_per_state`, scoped
    to AGENT-INFERRED REGIONS (state["resolved"][...]["region_id"], set by
    finalize_districts once infer_regions.py has run) instead of fixed
    administrative states. Unlike the per-state version, this runs TWO
    passes:

      1. INTRA-region — dominant-cluster pairs within the SAME region
         (`EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP` each), the direct analogue
         of extract_deflections_per_state's per-state pass. Because a region
         can genuinely span multiple states, `level` is always literally
         "intra-region" here (same "no new branch needed" reasoning
         extract_deflections_per_state's own docstring already gives for
         "intra-state") but unit_a/unit_b still resolve to each cluster's own
         STATE (via the existing `_unit_label`/`_highest_volume_district`) --
         showing genuine within-region state variation is the point, not
         redundant region-name repetition.

      2. INTER-region — a smaller top-K pass (`EXTRAHIGH_INTER_REGION_
         DEFLECTIONS_CAP`, flat across ALL region pairs, not per-region)
         comparing each region's single most-dominant cluster against every
         other region's, finally putting DeflectionLevel's long-unused
         "inter-region" value to work. unit_a/unit_b here are REGION names
         (via `_region_label`), since the contrast being drawn is genuinely
         between two regions, not two states.

    Reuses every pure helper (`_cluster_label`, `_cluster_texts`,
    `_total_volume_by_cluster`, `_highest_volume_district`) completely
    unchanged.
    """
    resolved = state.get("resolved", {})
    clusters = state.get("clusters", {})
    totals = _total_volume_by_cluster(resolved)

    dominant_by_region: dict[str, set[str]] = {}
    for rd in resolved.values():
        cluster_id = rd.get("dominant_cluster_id")
        region_id = rd.get("region_id")
        if not cluster_id or not region_id:
            continue
        dominant_by_region.setdefault(region_id, set()).add(cluster_id)

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REGION_DEFLECTION)

    async def _deflect_one_region(region_id: str, cluster_ids: set[str]) -> None:
        pairs = list(itertools.combinations(sorted(cluster_ids), 2))
        pairs.sort(key=lambda p: totals.get(p[0], 0) + totals.get(p[1], 0), reverse=True)
        pairs = pairs[:EXTRAHIGH_DEFLECTIONS_PER_REGION_CAP]

        async with semaphore:
            for cluster_a_id, cluster_b_id in pairs:
                label_a = _cluster_label(clusters, cluster_a_id)
                label_b = _cluster_label(clusters, cluster_b_id)
                texts_a = _cluster_texts(clusters, cluster_a_id)
                texts_b = _cluster_texts(clusters, cluster_b_id)

                point, confidence = await llm.extract_deflection(label_a, texts_a, label_b, texts_b)

                rd_a = _highest_volume_district(resolved, cluster_a_id)
                rd_b = _highest_volume_district(resolved, cluster_b_id)
                unit_a = _unit_label(rd_a)
                unit_b = _unit_label(rd_b)

                deflection_id = f"def-{region_id}-{cluster_a_id}-{cluster_b_id}"

                await emit(
                    DeflectionEvent(
                        query_run_id=state["query_run_id"],
                        id=deflection_id,
                        cluster_a=cluster_a_id,
                        cluster_b=cluster_b_id,
                        level="intra-region",  # type: ignore[arg-type]
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
                        level="intra-region",
                        unit_a=unit_a,
                        unit_b=unit_b,
                        point=point,
                        confidence=confidence,
                    )
                )
                state["deflections_found"] = len(state["deflections"])

    region_tasks = [
        asyncio.ensure_future(_deflect_one_region(region_id, cluster_ids))
        for region_id, cluster_ids in dominant_by_region.items()
        if len(cluster_ids) >= 2
    ]
    for finished in asyncio.as_completed(region_tasks):
        await finished

    # Pass 2 — inter-region: each region's own single highest-volume dominant
    # cluster stands in for that region, then a flat top-K pass across ALL
    # region-pairs (not per-region) surfaces only the most striking
    # cross-region contrasts, mirroring the pre-extrahigh flat top-6 cap.
    representative_cluster_by_region: dict[str, str] = {
        region_id: max(cluster_ids, key=lambda cid: totals.get(cid, 0))
        for region_id, cluster_ids in dominant_by_region.items()
    }
    region_ids_sorted = sorted(representative_cluster_by_region.keys())
    inter_pairs = list(itertools.combinations(region_ids_sorted, 2))
    inter_pairs.sort(
        key=lambda rp: (
            totals.get(representative_cluster_by_region[rp[0]], 0)
            + totals.get(representative_cluster_by_region[rp[1]], 0)
        ),
        reverse=True,
    )
    inter_pairs = inter_pairs[:EXTRAHIGH_INTER_REGION_DEFLECTIONS_CAP]

    for region_a, region_b in inter_pairs:
        cluster_a_id = representative_cluster_by_region[region_a]
        cluster_b_id = representative_cluster_by_region[region_b]
        label_a = _cluster_label(clusters, cluster_a_id)
        label_b = _cluster_label(clusters, cluster_b_id)
        texts_a = _cluster_texts(clusters, cluster_a_id)
        texts_b = _cluster_texts(clusters, cluster_b_id)

        point, confidence = await llm.extract_deflection(label_a, texts_a, label_b, texts_b)

        unit_a = _region_label(state, region_a)
        unit_b = _region_label(state, region_b)
        deflection_id = f"def-interregion-{region_a}-{region_b}"

        await emit(
            DeflectionEvent(
                query_run_id=state["query_run_id"],
                id=deflection_id,
                cluster_a=cluster_a_id,
                cluster_b=cluster_b_id,
                level="inter-region",  # type: ignore[arg-type]
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
                level="inter-region",
                unit_a=unit_a,
                unit_b=unit_b,
                point=point,
                confidence=confidence,
            )
        )
        state["deflections_found"] = len(state["deflections"])

    state["phase"] = "deflecting"
    found = state["deflections_found"]
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Analyzing deflections… {found} point{'s' if found != 1 else ''} of deflection "
                f"found across {len(dominant_by_region)} regions"
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

    Two-pass synthesis, PASS 1: when `state["regions"]` is populated
    (extrahigh, post region-inference), this pass is deliberately REGION-
    BLIND -- clusters_payload has state/region fields stripped and `mode` is
    downgraded to a non-extrahigh value so `llm.synthesize_answer` takes its
    existing, already-tuned non-extrahigh prompt branch (3-5 recommendation
    segments) instead of a third near-duplicate prompt variant. This
    produces the NATIONAL baseline; `condition_regions` (run next in the
    extrahigh graph topology) adds region-specific contrast on top and owns
    the pipeline's true completion event in that case -- this function
    deliberately does NOT mark the run "complete" when region-mode is active.
    """
    clusters = state.get("clusters", {})
    cluster_ids = state.get("cluster_order") or list(clusters.keys())
    is_region_mode = bool(state.get("regions"))

    clusters_payload: list[dict] = []
    for cid in cluster_ids:
        cluster = clusters.get(cid)
        if not cluster:
            continue
        entry: dict = {
            "id": cluster.get("id", cid),
            "label": cluster.get("label"),
            "summary": cluster.get("summary"),
            "postCount": len(cluster.get("post_ids") or []),
        }
        if not is_region_mode:
            # extrahigh-per-state legacy shape (no regions inferred this
            # run) -- still meaningful there, since without region-inference
            # a cluster's own state IS its one true geography, not a
            # representative shim. Omitted entirely in region-mode so pass 1
            # has zero region/state signal to condition on.
            entry["stateCode"] = cluster.get("state_code")
        clusters_payload.append(entry)

    deflections_payload = [dict(d) for d in state.get("deflections", [])]

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                "Synthesizing the national baseline answer…"
                if is_region_mode
                else "Synthesizing the consolidated answer…"
            ),
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
        # "high" (not "extrahigh") on purpose in region-mode -- see docstring.
        mode="high" if is_region_mode else state["mode"],
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

    # Stable, write-once snapshot of the just-built baseline -- both
    # condition_regions (pass 2) and condition_states (pass 3) read baseline
    # segments from HERE, never from `answer_segments` above, since by the
    # time pass 3 runs `answer_segments` also holds pass 2's own output.
    # Harmless to set for basic/medium/high too (never read there).
    state["baseline_answer_segments"] = list(state["answer_segments"])

    if is_region_mode:
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Baseline answer ready · conditioning {len(state['regions'])} regions…",
                phase="synthesizing",
                counts=_counts_from_state(state),
                progress=0.9,
            )
        )
        return state

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


# Mirrors _MAX_CONCURRENT_STATE_DEFLECTION/_MAX_CONCURRENT_REGION_DEFLECTION's
# naming/style: bounds how many regions condition concurrently, not how much
# LLM work each one does.
_MAX_CONCURRENT_REGION_SYNTHESIS = 6


def _region_clusters_payload(clusters: dict, region_id: str) -> list[dict]:
    return [
        {
            "id": c.get("id"),
            "label": c.get("label"),
            "summary": c.get("summary"),
            "postCount": len(c.get("post_ids") or []),
        }
        for c in clusters.values()
        if c.get("region_id") == region_id
    ]


def _region_deflections_payload(deflections: list[dict], clusters: dict, region_id: str) -> list[dict]:
    """Only INTRA-region deflections belong to a single region -- an
    inter-region pair (see extract_deflections_per_region) is a contrast
    between two DIFFERENT regions, not something either one "owns" alone."""
    payload = []
    for d in deflections:
        if d.get("level") != "intra-region":
            continue
        cluster_a = clusters.get(d.get("cluster_a"))
        if cluster_a and cluster_a.get("region_id") == region_id:
            payload.append(dict(d))
    return payload


# ── Per-state (administrative) re-slicing, for condition_states below ───────
#
# Unlike _region_clusters_payload/_region_deflections_payload above (which can
# trust a region-mode ClusterState's OWN state_code, since that field is only
# ever a representative stand-in there and every cluster belongs to exactly
# one region), a cluster spanning two states inside one inferred region must
# be split ACROSS both states' payloads -- so these helpers re-derive true
# per-state membership from resolved[...]'s own state_code (each district's
# REAL administrative state, set by finalize_districts/resolve_districts from
# the district's own geography, never from any cluster) rather than filtering
# on a cluster's single state_code/region_id field.


def _cluster_volume_by_state(
    resolved: dict[str, ResolvedDistrictState], cluster_id: str
) -> dict[str, int]:
    """TRUE per-state volume for one cluster, aggregated from every
    resolved district's own state_code -- NOT the cluster's own,
    only-representative-in-region-mode state_code (see ClusterState's
    state_code docstring). A cluster whose posts span districts in two
    different states shows up here with a nonzero entry for BOTH -- the
    volume split this module's own plan was written to get right."""
    volumes: dict[str, int] = {}
    for rd in resolved.values():
        vol = rd.get("cluster_volumes", {}).get(cluster_id, 0)
        if not vol:
            continue
        state_code = rd.get("state_code")
        if not state_code:
            continue
        volumes[state_code] = volumes.get(state_code, 0) + vol
    return volumes


def _state_clusters_payload(
    clusters: dict, resolved: dict[str, ResolvedDistrictState], state_code: str
) -> list[dict]:
    """Per-state re-slice of every cluster's TRUE volume in `state_code`
    (via `_cluster_volume_by_state` above), instead of filtering clusters by
    their own (region-mode-only-representative) state_code field. A cluster
    with zero true volume in this state is omitted entirely -- e.g. a cluster
    whose region happens to also cover this state, but none of whose actual
    posts fall within it. `postCount` here is this state's own share of the
    cluster's volume, not the cluster's total across every state it spans."""
    payload: list[dict] = []
    for cluster in clusters.values():
        cluster_id = cluster.get("id")
        if not cluster_id:
            continue
        volume = _cluster_volume_by_state(resolved, cluster_id).get(state_code, 0)
        if volume <= 0:
            continue
        payload.append(
            {
                "id": cluster_id,
                "label": cluster.get("label"),
                "summary": cluster.get("summary"),
                "postCount": volume,
            }
        )
    return payload


def _state_deflections_payload(
    deflections: list[dict], resolved: dict[str, ResolvedDistrictState], state_code: str
) -> list[dict]:
    """Only INTRA-STATE deflections (extract_deflections_per_state's output)
    belong to a single state -- mirrors _region_deflections_payload's own
    level-gate, one level down. DeflectionState carries no state_code field
    of its own (unlike the region case, where a cluster's region_id field is
    trustworthy) -- membership is re-derived via `_highest_volume_district`,
    the SAME helper extract_deflections_per_state itself used to decide
    state_code_a/state_code_b when constructing each pair, rather than
    parsing the state_code back out of the deflection_id string."""
    payload = []
    for d in deflections:
        if d.get("level") != "intra-state":
            continue
        rd_a = _highest_volume_district(resolved, d.get("cluster_a"))
        if rd_a and rd_a.get("state_code") == state_code:
            payload.append(dict(d))
    return payload


def _state_districts_payload(resolved: dict[str, ResolvedDistrictState], state_code: str) -> list[dict]:
    """Per-district post-volume breakdown for one state, for
    condition_answer_for_state's `state_districts` input -- lets it name
    specific districts within the state when the source data supports it."""
    info_by_id = _district_info_by_id()
    payload = []
    for rd in resolved.values():
        if rd.get("state_code") != state_code:
            continue
        district_id = rd["district_id"]
        info = info_by_id.get(district_id, {})
        payload.append(
            {
                "districtId": district_id,
                "districtName": info.get("districtName") or district_id,
                "postCount": sum(rd.get("cluster_volumes", {}).values()),
            }
        )
    payload.sort(key=lambda d: d["postCount"], reverse=True)
    return payload


@lru_cache(maxsize=1)
def _state_name_by_code() -> dict[str, str]:
    """state_code -> state_name, derived from the same cached
    `_district_info_by_id()` this module already builds from the district
    gazetteer -- avoids a second file read (data/subreddit_map.py's own
    `_state_names_from_gazetteer` takes the RAW nested gazetteer shape, which
    this module doesn't otherwise load; this reduces the already-loaded flat
    per-district info instead)."""
    names: dict[str, str] = {}
    for info in _district_info_by_id().values():
        code = info.get("stateCode")
        name = info.get("stateName")
        if code and name and code not in names:
            names[code] = name
    return names


async def condition_regions(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode-only, PASS 2 of two-pass synthesis (see
    synthesize_answer's region-blind baseline pass above, which this node
    runs directly after in the extrahigh graph topology). Fans out ONE
    `llm.condition_answer_for_region` call per region -- concurrency-bounded
    by `_MAX_CONCURRENT_REGION_SYNTHESIS` -- asking how THAT region's actual
    clusters/deflections differ from the national baseline. Checks
    region_kb.py's persistent knowledge base first for a relevant past
    worldview digest to condition on, then persists this call's own output
    as a NEW snapshot for future runs to draw on (no extra LLM call needed
    for that -- it reuses this call's own output as the worldview text).
    Appends region-tagged segments to state["answer_segments"] after the
    baseline. `condition_states` (pass 3) runs directly after this node and
    now owns the pipeline's true completion event for extrahigh runs --
    synthesize_answer's own "Done" event is deliberately skipped in
    region-mode (see that function), and this node no longer owns it either
    now that a further pass follows it."""
    regions = state.get("regions") or {}
    clusters = state.get("clusters", {})
    deflections = state.get("deflections", [])
    # Read from the STABLE pass-1 snapshot, not the ever-growing
    # `answer_segments` -- see state.py's baseline_answer_segments docstring.
    baseline_segments = list(state.get("baseline_answer_segments") or [])

    # Skip any region with no real district membership (the UNK-REGION-style
    # sentinel bucket for geography-unresolvable posts, see infer_regions.py)
    # -- its posts already contributed to the region-blind baseline, and "in
    # Unresolved geography..." is not a real contrast to draw.
    conditionable_regions: dict[str, RegionState] = {
        rid: r for rid, r in regions.items() if r.get("district_ids")
    }
    total_regions = len(conditionable_regions)

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REGION_SYNTHESIS)
    regions_done = 0

    async def _condition_one_region(region_id: str, region: RegionState) -> None:
        region_clusters = _region_clusters_payload(clusters, region_id)
        if not region_clusters:
            return
        region_deflections = _region_deflections_payload(deflections, clusters, region_id)

        async with semaphore:
            conditioning = await get_region_conditioning(
                llm,
                region["name"],
                region["district_ids"],
                state["query"],
                exclude_query_run_id=state["query_run_id"],
            )
            past_worldview = conditioning["digest"] if conditioning else None

            segments = await llm.condition_answer_for_region(
                state["query"],
                state["query_type"],
                baseline_segments,
                region["name"],
                region_clusters,
                region_deflections,
                past_worldview,
                mode=state["mode"],
            )

        cleaned_segments = [s for s in (segments or []) if isinstance(s, dict) and s.get("text")]

        worldview_text = " ".join(s["text"] for s in cleaned_segments).strip()
        if worldview_text:
            region["worldview_text"] = worldview_text
            await persist_region_snapshot(
                query_run_id=state["query_run_id"],
                source_query=state["query"],
                region_name=region["name"],
                district_ids=region["district_ids"],
                state_codes=region["state_codes"],
                worldview_text=worldview_text,
                confidence=region["confidence"],
            )

        for seg in cleaned_segments:
            kwargs: dict = {"text": seg["text"], "region": region["name"], "region_id": region_id}
            if seg.get("kind") is not None:
                kwargs["kind"] = seg["kind"]
            cluster_id = seg.get("clusterId", seg.get("cluster_id"))
            if cluster_id is not None:
                kwargs["cluster_id"] = cluster_id
            if isinstance(seg.get("citations"), list) and seg["citations"]:
                kwargs["citations"] = list(seg["citations"])

            segment = AnswerSegment(**kwargs)
            await emit(AnswerChunkEvent(query_run_id=state["query_run_id"], segment=segment))
            state["answer_segments"].append(segment.model_dump(by_alias=True, exclude_none=True))

        nonlocal regions_done
        regions_done += 1
        progress = 0.9 + 0.08 * (regions_done / total_regions)
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Conditioned {regions_done}/{total_regions} regions ({region['name']})…",
                phase="synthesizing",
                counts=_counts_from_state(state),
                progress=progress,
            )
        )

    region_tasks = [
        asyncio.ensure_future(_condition_one_region(rid, r)) for rid, r in conditionable_regions.items()
    ]
    for finished in asyncio.as_completed(region_tasks):
        await finished

    # NOT the run's completion event anymore -- condition_states (pass 3)
    # runs directly after this node in extrahigh's topology and now owns
    # that. This is a handoff ticker: synthesis is still ongoing.
    state["phase"] = "synthesizing"
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Conditioned {total_regions} region{'s' if total_regions != 1 else ''} · "
                "conditioning states…"
            ),
            phase="synthesizing",
            counts=_counts_from_state(state),
            progress=0.94,
        )
    )
    return state


# Mirrors _MAX_CONCURRENT_REGION_SYNTHESIS's naming/style: bounds how many
# states condition concurrently, not how much LLM work each one does.
_MAX_CONCURRENT_STATE_SYNTHESIS = 6


async def condition_states(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode-only, PASS 3 of three-pass synthesis -- runs directly
    after `condition_regions` (pass 2) in the extrahigh graph topology, as
    the new true last node. Fans out ONE `llm.condition_answer_for_state`
    call per ADMINISTRATIVE STATE present in `state["resolved"]` --
    concurrency-bounded by `_MAX_CONCURRENT_STATE_SYNTHESIS` -- asking how
    THAT state's actual research/social-media discourse differs from the
    SAME stable pass-1 baseline `condition_regions` was given
    (`state["baseline_answer_segments"]`, never the ever-growing
    `answer_segments`, which by now also holds pass 2's own output).

    Unlike `condition_regions`, this call is deliberately given TWO
    separately-sourced inputs -- mainstream/official research documents
    (`_state_research_documents`, this state's own slice of
    `state["research_documents"]`, filtered by each document's
    `source_state_code` -- see gather_research_per_state) and social-media
    viewpoint clusters/deflections (`_state_clusters_payload`/
    `_state_deflections_payload`, re-aggregated from each district's TRUE
    state_code so a cluster spanning multiple states is split correctly
    across each one's payload) -- so its produced segments keep the two
    source types explicitly separate, never blended into one paragraph. See
    `connectors/base.py`'s `condition_answer_for_state` docstring for the
    full contract.

    Appends state-tagged segments to state["answer_segments"] after the
    baseline and region-conditioned segments, and owns the pipeline's true
    completion event for extrahigh runs, as the new true last node
    (synthesize_answer's own "Done" event is skipped in region-mode, and
    condition_regions no longer emits it either -- see both docstrings)."""
    resolved = state.get("resolved", {})
    clusters = state.get("clusters", {})
    deflections = state.get("deflections", [])
    research_documents = state.get("research_documents") or []
    baseline_segments = list(state.get("baseline_answer_segments") or [])

    state_codes = sorted({rd["state_code"] for rd in resolved.values() if rd.get("state_code")})
    total_states = len(state_codes)

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_STATE_SYNTHESIS)
    states_done = 0

    async def _condition_one_state(state_code: str) -> None:
        state_name = _state_name_by_code().get(state_code, state_code)
        state_clusters = _state_clusters_payload(clusters, resolved, state_code)
        state_research_documents = [
            d
            for d in research_documents
            if isinstance(d, dict) and d.get("source_state_code") == state_code
        ]
        if not state_clusters and not state_research_documents:
            return
        state_deflections = _state_deflections_payload(deflections, resolved, state_code)
        state_districts = _state_districts_payload(resolved, state_code)

        async with semaphore:
            segments = await llm.condition_answer_for_state(
                state["query"],
                state["query_type"],
                baseline_segments,
                state_name,
                state_research_documents,
                state_clusters,
                state_deflections,
                state_districts,
                mode=state["mode"],
            )

        cleaned_segments = [s for s in (segments or []) if isinstance(s, dict) and s.get("text")]

        for seg in cleaned_segments:
            kwargs: dict = {"text": seg["text"], "state": state_name, "state_code": state_code}
            if seg.get("kind") is not None:
                kwargs["kind"] = seg["kind"]
            cluster_id = seg.get("clusterId", seg.get("cluster_id"))
            if cluster_id is not None:
                kwargs["cluster_id"] = cluster_id
            if isinstance(seg.get("citations"), list) and seg["citations"]:
                kwargs["citations"] = list(seg["citations"])

            segment = AnswerSegment(**kwargs)
            await emit(AnswerChunkEvent(query_run_id=state["query_run_id"], segment=segment))
            state["answer_segments"].append(segment.model_dump(by_alias=True, exclude_none=True))

        nonlocal states_done
        states_done += 1
        progress = 0.94 + 0.05 * (states_done / total_states)
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Conditioned {states_done}/{total_states} states ({state_name})…",
                phase="synthesizing",
                counts=_counts_from_state(state),
                progress=progress,
            )
        )

    state_tasks = [asyncio.ensure_future(_condition_one_state(code)) for code in state_codes]
    for finished in asyncio.as_completed(state_tasks):
        await finished

    state["phase"] = "complete"
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Done · {state.get('posts_collected', 0)} posts · "
                f"{state.get('districts_resolved', 0)} districts · "
                f"{state.get('clusters_found', 0)} clusters · "
                f"{state.get('deflections_found', 0)} deflections · "
                f"{len(state.get('regions') or {})} regions · "
                f"{total_states} states"
            ),
            phase="complete",
            counts=_counts_from_state(state),
            progress=1.0,
        )
    )
    return state
