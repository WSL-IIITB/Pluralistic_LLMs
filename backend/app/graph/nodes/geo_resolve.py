"""
Geography-first resolution — extrahigh-mode-only stage inserted between
research and clustering: `source -> research -> **geo_resolve** -> cluster ->
resolve -> deflect -> synthesize`. basic/medium/high never run this node; they
keep resolving geography AFTER clustering (see resolve_district.py's module
docstring for why that ordering exists there).

`resolve_district.py`'s `_resolve_post` is already pure geography — it
returns `(district_id, state_code, method, confidence)` via the existing
fallback chain (subreddit lookup -> place-NER -> script/language -> LLM
geolocation -> unresolved) with zero dependency on `cluster_id`. Only its
caller (`resolve_districts`) couples it to clustering, by filtering to posts
that already have a `cluster_id` and by immediately aggregating volume
per-cluster. This node instead calls `_resolve_post` directly on EVERY post
(no cluster_id exists yet at this point in the extrahigh pipeline), writes
the result back onto each post, and buckets post ids by resolved state so
`cluster_viewpoints_per_state` can cluster each state's posts independently.
The aggregation half (`_apply_resolution`, unchanged) runs later, once
clustering has happened, via `resolve_district.py`'s `finalize_districts`.
"""

from __future__ import annotations

import asyncio

from ...connectors.base import LLMClient
from ...schema import CollectionCounts, StatusEvent
from ..state import EmitFn, PipelineState
from .resolve_district import _build_indices, _resolve_post

# Mirrors resolve_district.py's own batch size -- same reasoning (concurrent
# lookups within a batch, smooth progress ticks across batches).
_BATCH_SIZE = 10

# This stage spans the same progress slice resolve_districts occupies today
# for basic/medium/high (0.15-0.5) shifted slightly since research (0.12-0.32)
# already runs before it in the extrahigh topology -- see build.py.
_PROGRESS_START = 0.32
_PROGRESS_END = 0.5

# Sentinel bucket for posts whose geography couldn't be resolved at all --
# keeps them in the corpus (clustered as their own group) rather than
# silently dropped, consistent with this codebase's "never lose data to a
# quality gate silently" stance (see build.py's _filter_by_relevance).
UNKNOWN_STATE = "UNK"


async def resolve_posts_geography(
    state: PipelineState,
    emit: EmitFn,
    llm: LLMClient,
    gazetteer: dict,
    subreddit_lookup,
    script_region_detect,
) -> PipelineState:
    """Resolve every post in state["posts"] to (district_id, state_code,
    method, confidence) BEFORE clustering, writing the result onto each post
    and bucketing post ids by state into state["posts_by_state"]. Returns the
    mutated state."""
    posts = state["posts"]
    total = len(posts)
    state["phase"] = "resolving"

    if total == 0:
        return state

    district_by_id, first_district_for_state = _build_indices(gazetteer)
    posts_by_state = state["posts_by_state"]

    processed = 0
    for batch_start in range(0, total, _BATCH_SIZE):
        batch = posts[batch_start : batch_start + _BATCH_SIZE]

        # Read-only lookups (including any LLM calls) run concurrently within
        # a batch -- same reasoning as resolve_district.py's resolve_districts.
        resolutions = await asyncio.gather(
            *(
                _resolve_post(
                    post,
                    llm,
                    gazetteer,
                    subreddit_lookup,
                    script_region_detect,
                    district_by_id,
                    first_district_for_state,
                )
                for post in batch
            )
        )

        for post, resolution in zip(batch, resolutions):
            if resolution is not None:
                district_id, state_code, method, confidence = resolution
                post["district_id"] = district_id
                post["state_code"] = state_code
                post["resolution_method"] = method
                post["resolution_confidence"] = confidence
            posts_by_state.setdefault(post["state_code"] or UNKNOWN_STATE, []).append(post["id"])

        processed += len(batch)
        progress = _PROGRESS_START + (_PROGRESS_END - _PROGRESS_START) * (processed / total)
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Resolved geography for {processed}/{total} posts across "
                    f"{len(posts_by_state)} states…"
                ),
                phase="resolving",
                counts=CollectionCounts(
                    posts_collected=state["posts_collected"],
                    districts_resolved=state["districts_resolved"],
                    clusters_found=state["clusters_found"],
                    deflections_found=state["deflections_found"],
                ),
                progress=progress,
            )
        )

    return state
