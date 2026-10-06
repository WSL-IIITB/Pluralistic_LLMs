"""Measure whether one Karnataka-wide answer represents every region.

The original metric made a separate persona-free baseline for every region.
That could only measure gender variation inside a region; it could not answer
the product question of what is lost when one statewide answer replaces
region-aware answers.

This node instead uses the Karnataka-wide overview already synthesized in the
run as one shared baseline. Each regional persona reply is compared against it
with local sentence embeddings. Lower similarity means the generic statewide
answer represents that regional response less well. Gender is retained only as
a secondary diagnostic.
"""

from __future__ import annotations

import asyncio

import numpy as np

from ...connectors.llm import _local_semantic_embed
from ...karnataka import persona_regions
from ...schema import CollectionCounts, PersonaSimilarityRegionEvent, StatusEvent
from ..state import EmitFn, PipelineState
from .persona_answers import reply_text

_CONCURRENCY = 4


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


async def _reply_vector(text: str) -> np.ndarray:
    return _unit(np.array(await _local_semantic_embed([text]), dtype=float))[0]


def _statewide_baseline(state: PipelineState) -> str:
    """The overview written before the region-specific persona replies."""
    return " ".join(
        segment["text"].strip()
        for segment in state.get("answer_segments") or []
        if segment.get("text") and not segment.get("regionId")
    )


async def measure_persona_similarity(state: PipelineState, emit: EmitFn, llm: object) -> PipelineState:
    del llm  # This comparison reuses the already-generated statewide overview.
    regions = [spec for spec in persona_regions() if spec["id"] in (state.get("region_replies") or {})]
    baseline_text = _statewide_baseline(state)
    if not baseline_text:
        raise ValueError("Karnataka-wide baseline answer was not generated")
    baseline_vec = await _reply_vector(baseline_text)
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    done = 0
    total = len(regions)

    def _counts() -> CollectionCounts:
        return CollectionCounts(
            posts_collected=state["posts_collected"],
            districts_resolved=state["districts_resolved"],
            clusters_found=state["clusters_found"],
            deflections_found=state["deflections_found"],
            sources_gathered=len(state.get("research_documents") or []),
            regions_found=len(state.get("region_stats") or {}),
        )

    async def _one(spec: dict) -> None:
        nonlocal done
        region_id = spec["id"]
        replies = state["region_replies"].get(region_id) or {}
        male_text = reply_text((replies.get("male") or {}).get("segments") or [])
        female_text = reply_text((replies.get("female") or {}).get("segments") or [])
        try:
            if not male_text and not female_text:
                raise ValueError("no persona reply for this region this run")
            async with semaphore:
                male_similarity = float(baseline_vec @ await _reply_vector(male_text)) if male_text else None
                female_similarity = float(baseline_vec @ await _reply_vector(female_text)) if female_text else None
            if male_similarity is not None and female_similarity is not None:
                more_divergent = "male" if male_similarity < female_similarity else (
                    "female" if female_similarity < male_similarity else "equal"
                )
            else:
                more_divergent = None

            event = PersonaSimilarityRegionEvent(
                query_run_id=state["query_run_id"],
                region_id=region_id,
                region_name=spec["short_name"],
                status="ok",
                male_similarity=round(male_similarity, 3) if male_similarity is not None else None,
                female_similarity=round(female_similarity, 3) if female_similarity is not None else None,
                more_divergent_persona=more_divergent,
                baseline_reply=baseline_text,
                male_reply=male_text or None,
                female_reply=female_text or None,
            )
        except Exception as exc:  # noqa: BLE001 -- one region must not kill the others
            print(f"[measure_persona_similarity] {region_id} failed: {exc}", flush=True)
            event = PersonaSimilarityRegionEvent(
                query_run_id=state["query_run_id"],
                region_id=region_id,
                region_name=spec["short_name"],
                status="failed",
                error=str(exc)[:300],
            )
        await emit(event)
        done += 1
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Comparing regional answers with the Karnataka-wide overview {done}/{total} ({spec['short_name']})…",
                phase="synthesizing",
                counts=_counts(),
                progress=0.85 + 0.05 * done / max(1, total),
            )
        )

    await asyncio.gather(*(_one(spec) for spec in regions))

    return state
