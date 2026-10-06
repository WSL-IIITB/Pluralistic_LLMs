"""
Resolves every post to one of Karnataka's four persona regions (or the
non-persona statewide bucket), BEFORE clustering, so each region's viewpoints
cluster independently (cluster_viewpoints_per_region).

Per-post chain, strongest signal first:
  1. subreddit (r/bangalore -> Bengaluru Urban -> Mysuru-Bengaluru)
  2. places the post names, via the Karnataka-augmented gazetteer (districts,
     towns, alt spellings) or a region's own name ("Malnad", "Tulu Nadu")
  3. a region name anywhere in the raw text
  4. LLM geolocation, validated against the same gazetteer
  5. "search_context": the region whose targeted search surfaced the post
  6. statewide fallback -- unless the post is clearly about somewhere outside
     Karnataka, in which case it is dropped (out of scope for this product).

Research-derived posts arrive already region-attributed (research.py) and pass
straight through.
"""

from __future__ import annotations

import asyncio

from ...connectors.base import LLMClient
from ...karnataka import (
    karnataka_state_code,
    load_karnataka_gazetteer,
    normalize_place,
    persona_regions,
    region_from_alias,
    region_of_district,
    statewide_region_id,
    statewide_region_name,
)
from ...schema import CollectionCounts, RegionDefinedEvent, StatusEvent
from ..state import EmitFn, PipelineState, RawPost, RegionState

_CONCURRENCY = 6
_PROGRESS_START = 0.32
_PROGRESS_END = 0.5

OUTSIDE = "outside"


async def _resolve(post: RawPost, llm: LLMClient, gazetteer: dict, subreddit_lookup) -> tuple[str, str, str, str | None]:
    """(region_id | OUTSIDE, method, confidence, district_id)."""
    ka = karnataka_state_code()
    district_region = region_of_district()
    statewide = statewide_region_id()
    elsewhere = False

    def _from_district(district_id: str | None, state_code: str | None) -> str | None:
        nonlocal elsewhere
        if not district_id:
            return None
        if state_code == ka and district_id in district_region:
            return district_region[district_id]
        elsewhere = True
        return None

    if post["platform"] == "reddit":
        entry = subreddit_lookup(post["source_hint"]) or {}
        region = _from_district(entry.get("district_id"), entry.get("state_code"))
        if region:
            return region, "city_subreddit", "high", entry.get("district_id")
        if entry.get("state_code") == ka:
            return statewide, "city_subreddit", "medium", None

    places = await llm.extract_place_mentions(post["text"])
    mentions_karnataka = False
    for place in places:
        key = normalize_place(place)
        if key == "karnataka":
            mentions_karnataka = True
            continue
        alias_region = region_from_alias(place)
        if alias_region:
            return alias_region, "place_ner", "medium", None
        cand = (gazetteer.get(key) or [None])[0]
        if cand:
            region = _from_district(cand.get("districtId"), cand.get("stateCode"))
            if region:
                return region, "place_ner", "high", cand["districtId"]

    alias_region = region_from_alias(f"{post['text']} {post['source_hint']}")
    if alias_region:
        return alias_region, "place_ner", "medium", None

    if not mentions_karnataka:
        district_id, confidence = await llm.geolocate(post["text"], post["source_hint"])
        if district_id:
            cand = next((c for cands in gazetteer.values() for c in cands if c.get("districtId") == district_id), None)
            region = _from_district(district_id, cand.get("stateCode") if cand else None)
            if region:
                return region, "llm_geolocation", confidence, district_id

    if post.get("source_region_id") and post["source_region_id"] != statewide:
        return post["source_region_id"], "search_context", "low", None
    if elsewhere and not mentions_karnataka:
        return OUTSIDE, "unresolved", "low", None
    return statewide, "state_fallback", "medium" if mentions_karnataka else "low", None


def _region_states() -> dict[str, RegionState]:
    ka = karnataka_state_code()
    regions: dict[str, RegionState] = {}
    for spec in persona_regions():
        regions[spec["id"]] = RegionState(
            id=spec["id"],
            name=spec["short_name"],
            justification=spec["definition"],
            district_ids=list(spec["district_ids"]),
            state_codes=[ka],
            confidence="high",
            worldview_text="",
        )
    regions[statewide_region_id()] = RegionState(
        id=statewide_region_id(),
        name=statewide_region_name(),
        justification="Posts about Karnataka as a whole, not any one region. No persona.",
        district_ids=[],
        state_codes=[ka],
        confidence="medium",
        worldview_text="",
    )
    return regions


async def resolve_regions(
    state: PipelineState, emit: EmitFn, llm: LLMClient, gazetteer: dict, subreddit_lookup
) -> PipelineState:
    state["phase"] = "resolving"
    state["regions"] = _region_states()
    for region in state["regions"].values():
        await emit(
            RegionDefinedEvent(
                query_run_id=state["query_run_id"],
                region_id=region["id"],
                name=region["name"],
                justification=region["justification"],
                district_ids=region["district_ids"],
                state_codes=region["state_codes"],
                confidence=region["confidence"],  # type: ignore[arg-type]
            )
        )

    ka_gazetteer = load_karnataka_gazetteer(gazetteer)
    posts = state["posts"]
    pending = [p for p in posts if not p.get("region_id")]
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    done = 0

    async def _one(post: RawPost) -> None:
        nonlocal done
        async with semaphore:
            try:
                region_id, method, confidence, district_id = await _resolve(post, llm, ka_gazetteer, subreddit_lookup)
            except Exception as exc:  # noqa: BLE001 -- one post must not kill the stage
                print(f"[resolve_regions] post {post['id']} failed, keeping statewide: {exc}", flush=True)
                region_id, method, confidence, district_id = statewide_region_id(), "state_fallback", "low", None
        post["region_id"] = region_id
        post["resolution_method"] = method
        post["resolution_confidence"] = confidence
        post["district_id"] = district_id
        post["state_code"] = karnataka_state_code() if region_id != OUTSIDE else None
        done += 1
        if done % 10 == 0 or done == len(pending):
            await emit(
                StatusEvent(
                    query_run_id=state["query_run_id"],
                    ticker=f"Placed {done}/{len(pending)} posts into Karnataka's regions…",
                    phase="resolving",
                    counts=CollectionCounts(
                        posts_collected=state["posts_collected"],
                        districts_resolved=state["districts_resolved"],
                        clusters_found=state["clusters_found"],
                        deflections_found=state["deflections_found"],
                    ),
                    progress=_PROGRESS_START + (_PROGRESS_END - _PROGRESS_START) * done / max(1, len(pending)),
                )
            )

    await asyncio.gather(*(_one(p) for p in pending))

    kept = [p for p in posts if p["region_id"] != OUTSIDE]
    dropped = len(posts) - len(kept)
    if dropped:
        print(f"[resolve_regions] dropped {dropped} post(s) about places outside Karnataka", flush=True)
    state["posts"] = kept
    state["posts_collected"] = len(kept)
    state["posts_by_region"] = {}
    for post in kept:
        state["posts_by_region"].setdefault(post["region_id"], []).append(post["id"])
    state["districts_resolved"] = len({p["district_id"] for p in kept if p.get("district_id")})

    counts = ", ".join(
        f"{state['regions'][rid]['name']} {len(ids)}" for rid, ids in state["posts_by_region"].items()
    )
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=f"{len(kept)} posts placed ({counts or 'none'}) · clustering viewpoints per region…",
            phase="resolving",
            counts=CollectionCounts(
                posts_collected=state["posts_collected"],
                districts_resolved=state["districts_resolved"],
                clusters_found=state["clusters_found"],
                deflections_found=state["deflections_found"],
                regions_found=len(state["posts_by_region"]),
            ),
            progress=_PROGRESS_END,
        )
    )
    return state


_TIER_RANK = {"low": 0, "medium": 1, "high": 2}
_RANK_TIER = {v: k for k, v in _TIER_RANK.items()}


async def aggregate_regions(state: PipelineState, emit: EmitFn) -> PipelineState:
    """After clustering: per (region, cluster) post volumes -> RegionResolvedEvents
    and state["region_stats"]. Sample posts reuse each cluster's already-
    paraphrased representative posts (no extra LLM calls)."""
    from collections import Counter

    from ...schema import RegionResolvedEvent, SamplePost

    by_region: dict[str, list[RawPost]] = {}
    for post in state["posts"]:
        if post.get("region_id") and post.get("cluster_id"):
            by_region.setdefault(post["region_id"], []).append(post)

    for region_id, posts in by_region.items():
        volumes = Counter(p["cluster_id"] for p in posts)
        ranks = sorted(_TIER_RANK.get(p.get("resolution_confidence") or "low", 0) for p in posts)
        confidence = _RANK_TIER[ranks[len(ranks) // 2]]
        method = Counter(p.get("resolution_method") or "unresolved" for p in posts).most_common(1)[0][0]
        state["region_stats"][region_id] = {
            "region_id": region_id,
            "cluster_volumes": dict(volumes),
            "dominant_cluster_id": volumes.most_common(1)[0][0],
            "confidence": confidence,
            "method": method,
        }
        for cluster_id, volume in volumes.most_common():
            reps = (state["clusters"].get(cluster_id) or {}).get("representative_posts") or []
            await emit(
                RegionResolvedEvent(
                    query_run_id=state["query_run_id"],
                    region_id=region_id,
                    cluster_id=cluster_id,
                    volume=volume,
                    confidence=confidence,  # type: ignore[arg-type]
                    method=method,  # type: ignore[arg-type]
                    sample_posts=[SamplePost.model_validate(r) for r in reps] or None,
                )
            )
    return state
