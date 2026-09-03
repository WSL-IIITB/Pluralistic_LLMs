"""
District resolution node — third pipeline stage (source -> cluster ->
**resolve_district** -> deflection -> synthesize).

By the time this node runs, every post in `state["posts"]` already carries a
`cluster_id` (set by the clustering stage) — `district_resolved` events need a
clusterId, which is why clustering runs before this node (see
../state.py's module docstring). This node's only job is geography: map each
post to an Indian district and aggregate volume per (district, cluster).

Fallback chain per post (cheapest/highest-confidence signal first):
  1. `city_subreddit` — reddit posts: static subreddit -> district lookup
     (`subreddit_lookup`, e.g. app.data.subreddit_map.lookup_subreddit).
  2. `place_ner` — LLM-extracted place mentions matched against the district
     gazetteer (exact district-name match -> "high"; state-name-fallback
     match -> "medium").
  3. `script_language` — Indic-script heuristic (`script_region_detect`, e.g.
     app.data.language_regions.detect_script_region) gives at best a STATE,
     never a district, so a representative district within that state is
     picked and the result is always capped at "medium" confidence and
     flagged `is_state_fallback`.
  4. `llm_geolocation` — last-resort LLM guess, validated against the
     gazetteer before being trusted.
  5. `unresolved` — none of the above produced a valid district. Counted
     toward `posts_collected` (we did process the post) but NOT toward
     `districts_resolved`, and no `district_resolved` event is emitted for it.

Both `subreddit_lookup` and `script_region_detect` are accepted as plain
callables (not imported directly) so this module has no hard import
dependency on exactly where those data tables live.

Events are batched (~8-15 posts per batch): one `DistrictResolvedEvent` per
district touched in the batch (volume = the INCREMENTAL count added this
batch, not the running total — the frontend store accumulates) plus one
`StatusEvent` with progress climbing across the whole resolution pass.

Dominant-cluster nuance (mirrors a frontend bug fix — do not regress it): a
district accumulates volume across *all* clusters it's seen, and its
`dominant_cluster_id` is recomputed (argmax of cluster_volumes) on every
update, but `confidence` / `method` / `is_state_fallback` are only ever
overwritten by a resolution whose cluster IS (or just became) that recomputed
dominant cluster. A lower- or higher-confidence hit for a *non*-dominant
cluster must never clobber what's displayed for the district.
"""

from __future__ import annotations

import asyncio
import re

from ...connectors.base import LLMClient
from ...schema import CollectionCounts, DistrictResolvedEvent, SamplePost, StatusEvent
from ..state import EmitFn, PipelineState, RawPost, ResolvedDistrictState

# Posts processed per emitted batch of events -- small enough for smooth
# progress updates, large enough to not spam one event per post.
_BATCH_SIZE = 10

# Resolution spans this slice of overall run progress (mirrors StatusEvent
# events from other stages bracketing their own phase).
_PROGRESS_START = 0.15
_PROGRESS_END = 0.5

_TIER_RANK = {"low": 0, "medium": 1, "high": 2}
_STATE_FALLBACK_METHODS = ("script_language", "state_fallback")

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_name(name: str) -> str:
    """Mirror app/data/build_gazetteer.py's `normalize()` so place-name
    lookups actually land on the same keys the gazetteer was built with."""
    return _NORMALIZE_RE.sub(" ", name.lower()).strip()


def _cap_medium(confidence: str) -> str:
    """script_region_detect should only ever return "medium"/"low", but cap
    defensively -- a district-level fallback signal must never claim "high"."""
    return "medium" if _TIER_RANK.get(confidence, 0) > _TIER_RANK["medium"] else confidence


def _is_state_fallback_method(method: str) -> bool:
    return method in _STATE_FALLBACK_METHODS


def _build_indices(gazetteer: dict) -> tuple[dict[str, dict], dict[str, str]]:
    """One-time scan over the gazetteer (748ish keys, each a list of candidate
    dicts) so per-post lookups below don't rescan it from scratch every time:
      - district_by_id: districtId -> its candidate entry (first occurrence)
      - first_district_for_state: stateCode -> first districtId encountered
        for that state (in gazetteer iteration order), for the
        script_language fallback's "any district in this state" pick.
    """
    district_by_id: dict[str, dict] = {}
    first_district_for_state: dict[str, str] = {}
    for candidates in gazetteer.values():
        for cand in candidates:
            district_id = cand.get("districtId")
            state_code = cand.get("stateCode")
            if not district_id:
                continue
            if district_id not in district_by_id:
                district_by_id[district_id] = cand
            if state_code and state_code not in first_district_for_state:
                first_district_for_state[state_code] = district_id
    return district_by_id, first_district_for_state


async def _resolve_post(
    post: RawPost,
    llm: LLMClient,
    gazetteer: dict,
    subreddit_lookup,
    script_region_detect,
    district_by_id: dict[str, dict],
    first_district_for_state: dict[str, str],
) -> tuple[str, str, str, str] | None:
    """Resolve one post to (district_id, state_code, method, confidence), or
    None if unresolved. Implements the fallback chain from the module
    docstring, stopping at the first stage that produces a result."""

    # 1. Reddit subreddit lookup -- cheapest, highest-confidence signal.
    if post["platform"] == "reddit":
        entry = subreddit_lookup(post["source_hint"])
        if entry and entry.get("district_id"):
            return (
                entry["district_id"],
                entry["state_code"],
                "city_subreddit",
                entry.get("confidence") or "high",
            )
        # Either unknown subreddit, or a known state/pan-India one with no
        # single district -- fall through to place NER either way.

    # 2. LLM place-mention extraction against the district gazetteer.
    places = await llm.extract_place_mentions(post["text"])
    for place in places:
        key = _normalize_name(place)
        candidates = gazetteer.get(key)
        if not candidates:
            continue
        cand = candidates[0]
        district_name_key = _normalize_name(cand.get("districtName", ""))
        confidence = "high" if key == district_name_key else "medium"
        return (cand["districtId"], cand["stateCode"], "place_ner", confidence)

    # 3. Indic-script heuristic -> state-level fallback (never full district
    #    precision, so always at most "medium" and flagged is_state_fallback
    #    by the caller).
    state_code, script_confidence = script_region_detect(post["text"])
    if state_code is not None:
        district_id = first_district_for_state.get(state_code)
        if district_id is not None:
            return (district_id, state_code, "script_language", _cap_medium(script_confidence))

    # 4. Last-resort LLM geolocation, validated against the gazetteer.
    district_id, llm_confidence = await llm.geolocate(post["text"], post["source_hint"])
    if district_id:
        cand = district_by_id.get(district_id)
        if cand is not None:
            return (district_id, cand["stateCode"], "llm_geolocation", llm_confidence)

    # 5. Nothing resolved.
    return None


async def _apply_resolution(
    state: PipelineState,
    llm: LLMClient,
    district_id: str,
    state_code: str,
    cluster_id: str,
    method: str,
    confidence: str,
    post: RawPost,
    region_id: str | None = None,
) -> None:
    """Accumulate one resolved post into state["resolved"][district_id],
    mirroring the exact dominant-cluster nuance described in the module
    docstring. `region_id` (extrahigh-only, None for basic/medium/high) is
    set once at entry creation only -- unlike confidence/method/
    is_state_fallback, a district belongs to exactly one region for the
    whole run, so there's no per-cluster-update nuance to apply here."""
    resolved = state["resolved"]
    entry = resolved.get(district_id)
    if entry is None:
        entry = ResolvedDistrictState(
            district_id=district_id,
            state_code=state_code,
            cluster_volumes={},
            dominant_cluster_id=cluster_id,
            method=method,
            confidence=confidence,
            is_state_fallback=_is_state_fallback_method(method),
            sample_posts=[],
            region_id=region_id,
        )
        resolved[district_id] = entry

    cluster_volumes = entry["cluster_volumes"]
    cluster_volumes[cluster_id] = cluster_volumes.get(cluster_id, 0) + 1

    dominant_cluster_id = max(cluster_volumes.items(), key=lambda kv: kv[1])[0]
    entry["dominant_cluster_id"] = dominant_cluster_id

    # Only the (possibly-newly-)dominant cluster's own event may overwrite
    # these fields -- a non-dominant cluster's resolution, however confident,
    # must never clobber what's shown for the district's actual dominant
    # viewpoint (this is the exact bug the frontend review caught).
    if cluster_id == dominant_cluster_id:
        entry["confidence"] = confidence
        entry["method"] = method
        entry["is_state_fallback"] = _is_state_fallback_method(method)

    if len(entry["sample_posts"]) < 3:
        paraphrase = await llm.paraphrase(post["text"])
        entry["sample_posts"].append(
            {
                "id": post["id"],
                "platform": post["platform"],
                "paraphrase": paraphrase,
                "cluster_id": cluster_id,
                "url": post.get("permalink"),
            }
        )


def _district_event_for(state: PipelineState, district_id: str, volume: int) -> DistrictResolvedEvent:
    entry = state["resolved"][district_id]
    sample_posts = (
        [
            SamplePost(
                id=p["id"],
                platform=p["platform"],
                paraphrase=p["paraphrase"],
                cluster_id=p.get("cluster_id"),
                url=p.get("url"),
            )
            for p in entry["sample_posts"]
        ]
        if entry["sample_posts"]
        else None
    )
    return DistrictResolvedEvent(
        query_run_id=state["query_run_id"],
        district_id=district_id,
        state_code=entry["state_code"],
        cluster_id=entry["dominant_cluster_id"],
        confidence=entry["confidence"],
        volume=volume,
        method=entry["method"],
        is_state_fallback=entry["is_state_fallback"],
        sample_posts=sample_posts,
        region_id=entry.get("region_id"),
    )


async def resolve_districts(
    state: PipelineState,
    emit: EmitFn,
    llm: LLMClient,
    gazetteer: dict,
    subreddit_lookup,
    script_region_detect,
) -> PipelineState:
    """Resolve every post in state["posts"] to a district, aggregate volume
    per (district, cluster), and emit batched district_resolved/status
    events. Returns the mutated state."""
    posts = state["posts"]
    total = len(posts)
    state["phase"] = "resolving"

    if total == 0:
        state["districts_resolved"] = len(state["resolved"])
        return state

    district_by_id, first_district_for_state = _build_indices(gazetteer)

    processed = 0
    for batch_start in range(0, total, _BATCH_SIZE):
        batch = posts[batch_start : batch_start + _BATCH_SIZE]
        touched: dict[str, int] = {}  # district_id -> incremental volume this batch

        # The resolution lookup itself (steps 1-4, including any LLM calls) is
        # read-only, so every post in the batch can resolve CONCURRENTLY --
        # this is what keeps real (non-stub) LLM latency from stacking up
        # post-by-post. The subsequent _apply_resolution step mutates shared
        # state under an order-dependent invariant (dominant-cluster
        # recomputation), so that part still runs sequentially, in original
        # post order, once every resolution in the batch is back.
        eligible = [post for post in batch if post.get("cluster_id") is not None]
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
                for post in eligible
            )
        )

        for post, resolution in zip(eligible, resolutions):
            if resolution is None:
                continue
            cluster_id = post["cluster_id"]
            district_id, state_code, method, confidence = resolution
            await _apply_resolution(
                state, llm, district_id, state_code, cluster_id, method, confidence, post
            )
            touched[district_id] = touched.get(district_id, 0) + 1

        processed += len(batch)
        state["districts_resolved"] = len(state["resolved"])
        state["posts_collected"] += len(batch)

        for district_id, volume in touched.items():
            await emit(_district_event_for(state, district_id, volume))

        progress = _PROGRESS_START + (_PROGRESS_END - _PROGRESS_START) * (processed / total)
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Resolved {processed}/{total} posts to "
                    f"{state['districts_resolved']} districts"
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


# extrahigh-mode-only progress slice: geo_resolve (0.32-0.5) and
# cluster_viewpoints_per_state (0.5-0.68) already ran by the time this node
# starts -- see build.py's extrahigh topology.
_FINALIZE_PROGRESS_START = 0.68
_FINALIZE_PROGRESS_END = 0.78


async def finalize_districts(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode counterpart to `resolve_districts` -- everything BUT the
    `_resolve_post` gather step, which already ran up front in
    `geo_resolve.py`'s `resolve_posts_geography` (before clustering, so every
    state's posts could be clustered independently). By the time this runs,
    every post already carries `district_id`/`state_code`/`resolution_method`/
    `resolution_confidence` (from geo_resolve) and `cluster_id` (from
    `cluster_viewpoints_per_state`). Aggregates volume per (district, cluster)
    via the existing, unchanged `_apply_resolution` and emits
    `DistrictResolvedEvent`s exactly like `resolve_districts` does."""
    posts = state["posts"]
    total = len(posts)
    state["phase"] = "resolving"

    if total == 0:
        state["districts_resolved"] = len(state["resolved"])
        return state

    processed = 0
    for batch_start in range(0, total, _BATCH_SIZE):
        batch = posts[batch_start : batch_start + _BATCH_SIZE]
        touched: dict[str, int] = {}  # district_id -> incremental volume this batch

        # Purely bookkeeping (no LLM calls beyond the capped sample-post
        # paraphrase already inside _apply_resolution) -- runs sequentially,
        # in original post order, to preserve the exact same order-dependent
        # dominant-cluster invariant resolve_districts relies on.
        for post in batch:
            district_id = post.get("district_id")
            cluster_id = post.get("cluster_id")
            if district_id is None or cluster_id is None:
                continue
            await _apply_resolution(
                state,
                llm,
                district_id,
                post["state_code"],
                cluster_id,
                post["resolution_method"],
                post["resolution_confidence"],
                post,
                region_id=post.get("region_id"),
            )
            touched[district_id] = touched.get(district_id, 0) + 1

        processed += len(batch)
        state["districts_resolved"] = len(state["resolved"])
        state["posts_collected"] += len(batch)

        for district_id, volume in touched.items():
            await emit(_district_event_for(state, district_id, volume))

        progress = (
            _FINALIZE_PROGRESS_START
            + (_FINALIZE_PROGRESS_END - _FINALIZE_PROGRESS_START) * (processed / total)
        )
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Finalized {processed}/{total} posts across "
                    f"{state['districts_resolved']} districts"
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
