"""
Story Mode vs. the UIDAI/NITI official dominant-factor data.

Story Mode's answer (this run's per-region persona replies, both variants,
plus the Karnataka-wide overview) comes from social posts, web research and
each region's persona -- narrative, regional, plural. The UIDAI/NITI data
(../../niti_factors.py) comes from a district-level statistical model fitted
on official education/infrastructure indicators -- one number, no persona, no
regional voice.

For each region, and once for the whole state, this node puts both evidence
sources in front of the same model and asks for two things: how they differ,
and one consolidated answer that actually draws on both. Region scope only
compares/consolidates evidence that exists -- an empty `storyPoints` or
`officialFactors` list is passed through as empty, never papered over or
invented.

This is the pipeline's terminal node (replacing the old persona-vs-baseline
semantic-divergence stage): it is one call per region plus one for the
state (7 calls total, run 4 at a time), not the ~24+ the old design needed
per run, since it reuses replies already written by answer_regions rather
than generating fresh baseline/no-persona replies to compare against.
"""

from __future__ import annotations

import asyncio

from ...connectors.base import LLMClient
from ...karnataka import persona_regions
from ...niti_factors import NitiFactor, niti_factors_for_region, niti_factors_statewide
from ...schema import CollectionCounts, StatusEvent, StoryVsOfficialEvent
from ..state import EmitFn, PipelineState
from .persona_answers import reply_text

_CONCURRENCY = 4


def _story_points_for_region(state: PipelineState, region_id: str) -> list[str]:
    replies = (state.get("region_replies") or {}).get(region_id) or {}
    points = [reply_text(r.get("segments") or []) for r in replies.values()]
    return [p for p in points if p]


def _story_points_statewide(state: PipelineState) -> list[str]:
    # The region-blind Karnataka-wide overview (deflection_and_synthesis.synthesize_answer's output).
    return [
        seg["text"]
        for seg in state.get("answer_segments") or []
        if seg.get("text") and not seg.get("regionId")
    ]


def _factor_payload(factors: list[NitiFactor]) -> list[dict]:
    return [
        {
            "district": f["district_name"],
            "factor": f["factor"],
            "value": round(f["value"], 3),
            "method": f["method"],
        }
        for f in factors
    ]


async def compare_story_vs_official(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    state["phase"] = "synthesizing"
    jobs: list[tuple[str | None, str, list[str], list[dict]]] = [
        (
            r["id"],
            r["short_name"],
            _story_points_for_region(state, r["id"]),
            _factor_payload(niti_factors_for_region(r["id"])),
        )
        for r in persona_regions()
    ]
    jobs.append((None, "Karnataka (statewide)", _story_points_statewide(state), _factor_payload(niti_factors_statewide())))

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    done = 0
    total = len(jobs)

    def _counts() -> CollectionCounts:
        return CollectionCounts(
            posts_collected=state["posts_collected"],
            districts_resolved=state["districts_resolved"],
            clusters_found=state["clusters_found"],
            deflections_found=state["deflections_found"],
            sources_gathered=len(state.get("research_documents") or []),
            regions_found=len(state.get("region_stats") or {}),
        )

    async def _one(region_id: str | None, label: str, story_points: list[str], factors: list[dict]) -> None:
        nonlocal done
        scope = "statewide" if region_id is None else "region"
        try:
            async with semaphore:
                result = await llm.compare_story_vs_official(state["query"], label, story_points, factors)
            event = StoryVsOfficialEvent(
                query_run_id=state["query_run_id"],
                scope=scope,
                region_id=region_id,
                region_name=label,
                story_points=story_points,
                official_factors=factors,
                comparison=result.get("comparison", ""),
                consolidated_answer=result.get("consolidated_answer", ""),
                status="ok",
            )
        except Exception as exc:  # noqa: BLE001 -- one region/state failing must not kill the others
            print(f"[compare_story_vs_official] {label} failed: {exc}", flush=True)
            event = StoryVsOfficialEvent(
                query_run_id=state["query_run_id"],
                scope=scope,
                region_id=region_id,
                region_name=label,
                story_points=story_points,
                official_factors=factors,
                status="failed",
                error=str(exc)[:300],
            )
        await emit(event)
        done += 1
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Comparing Story Mode with UIDAI/NITI data {done}/{total} ({label})…",
                phase="synthesizing",
                counts=_counts(),
                progress=0.9 + 0.08 * done / max(1, total),
            )
        )

    await asyncio.gather(*(_one(*job) for job in jobs))

    state["phase"] = "complete"
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Done · {state['posts_collected']} posts · {len(state.get('research_documents') or [])} sources · "
                f"{state['clusters_found']} viewpoints · Story vs. UIDAI/NITI compared for {total} areas"
            ),
            phase="complete",
            counts=_counts(),
            progress=1.0,
        )
    )
    return state
