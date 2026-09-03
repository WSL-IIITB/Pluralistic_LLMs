"""
Region-inference — extrahigh-mode-only stage that will run AFTER geo_resolve
and BEFORE clustering: `source -> research -> geo_resolve -> **infer_regions**
-> cluster_viewpoints_per_region -> ...` (a later phase wires this into
build.py's graph topology; today this node is standalone/directly callable
but not yet spliced into the compiled graph).

Replaces per-STATE clustering with per-REGION clustering, where a region can
span several districts and cross multiple state boundaries -- inferred from
the data, not hardcoded. Design principle: numeric substrate first, LLM only
names/critiques/refines. Asking a model to freely partition districts from
raw text is exactly the failure-prone task small/local models are worst at
(dropped items, invented buckets, inconsistent counts) -- so the partition
itself is a deterministic silhouette-sweep over DISTRICT-averaged post
embeddings (same shape as cluster_viewpoints.py's `_choose_k_and_labels`, one
level up: post-level there, district-level here), and the LLM only:
  1. proposes a name + justification for each numeric group
     (`llm.propose_regions`)
  2. critiques the full proposed set for thematic coherence, geographic
     sanity, and granularity (`llm.critique_regions`)
  3. if rejected, revises -- rename / merge-two / move-one-flagged-district
     ONLY, never inventing a region or dropping a district
     (`llm.revise_regions`) -- bounded to
     `reasoning_modes.REGION_REVISION_ROUND_CAP` rounds, after which the
     current best partition is force-accepted. Mirrors connectors/llm.py's
     `_RESEARCH_TOOL_ROUND_CAP` pattern: convergence is code-enforced, never
     dependent on an LLM choosing to stop critiquing.

Every LLM output is code-validated both inside the LLMClient implementation
AND again here (defense in depth -- a Protocol implementation is a contract,
not a guarantee); a malformed propose/critique/revise result at any step
falls back to the raw numeric partition with an auto-generated name. This
node never blocks the pipeline on LLM cooperation.

NOT the same thing as data/subreddit_map.py's `_REGION_CODES` -- that's a
static 5-bucket macro-region table (north/east_northeast/central/west/south)
used only to interleave sourcing order across states. The regions this node
infers are per-query, agent-defined, and keyed by inferred worldview/content
similarity, not a fixed geographic bucket.
"""

from __future__ import annotations

import asyncio

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ...connectors.base import LLMClient
from ...reasoning_modes import (
    REGION_CLUSTER_K_MAX,
    REGION_CLUSTER_K_MIN,
    REGION_MIN_DISTRICTS_PER_REGION,
    REGION_REVISION_ROUND_CAP,
    _MIN_SILHOUETTE_FOR_REGION_SPLIT,
)
from ...schema import CollectionCounts, RegionDefinedEvent, StatusEvent
from ..state import EmitFn, PipelineState, RegionState
from .resolve_district import _build_indices

# Capped per-group/per-district so the propose/critique/revise prompts stay
# small regardless of how many posts a district resolved -- these calls only
# need enough sample text to ground a NAME, not the full corpus.
_MAX_SAMPLE_TEXTS_PER_GROUP = 6
_MAX_SAMPLE_TEXTS_PER_DISTRICT = 2
_MAX_SAMPLE_TEXT_CHARS = 200

# Placeholder progress marker -- this node sits between geo_resolve (which
# today ends at 0.5) and cluster_viewpoints_per_state/_per_region (which
# starts at 0.5), so it reports a single status tick at that same boundary.
# Retuned once this is spliced into build.py's topology.
_PROGRESS = 0.5

# Sentinel bucket for posts with no resolved district -- mirrors
# geo_resolve.py's UNKNOWN_STATE. Kept in the corpus (clustered as their own
# group downstream) rather than silently dropped, same "never lose data to a
# quality gate silently" stance used throughout this pipeline.
UNKNOWN_REGION = "UNK-REGION"


def _bucket_unknown_region(
    posts: list[dict],
    unresolved_indices: list[int],
    regions: dict[str, RegionState],
    posts_by_region: dict[str, list[str]],
) -> None:
    """Assigns every post with no resolved district to UNKNOWN_REGION,
    writing a synthetic RegionState so callers never need to special-case a
    region_id with no corresponding entry. No-op if there are none."""
    if not unresolved_indices:
        return
    post_ids = []
    for idx in unresolved_indices:
        posts[idx]["region_id"] = UNKNOWN_REGION
        post_ids.append(posts[idx]["id"])
    regions[UNKNOWN_REGION] = RegionState(
        id=UNKNOWN_REGION,
        name="Unresolved geography",
        justification="Posts whose district could not be resolved to any region.",
        district_ids=[],
        state_codes=[],
        confidence="low",
        worldview_text="",
    )
    posts_by_region[UNKNOWN_REGION] = post_ids


def _choose_region_k_and_labels(matrix: np.ndarray) -> tuple[int, list[int]]:
    """District-granularity counterpart to cluster_viewpoints.py's
    `_choose_k_and_labels` -- identical sweep-and-pick-best-silhouette shape,
    parameterized on the REGION_* constants instead of EXTRAHIGH_CLUSTER_*.
    Deliberately duplicated rather than imported/shared: that function is
    private to cluster_viewpoints.py, which already duplicates its own
    non-extrahigh sibling for the same "keep independently-evolving stages
    decoupled" reason used throughout this pipeline."""
    n = matrix.shape[0]
    if n < 2 * REGION_MIN_DISTRICTS_PER_REGION:
        return 1, [0] * n
    k_max = min(REGION_CLUSTER_K_MAX, n // REGION_MIN_DISTRICTS_PER_REGION, n - 1)
    if k_max < REGION_CLUSTER_K_MIN:
        return 1, [0] * n
    best_k, best_labels, best_score = REGION_CLUSTER_K_MIN, None, -1.0
    for k in range(REGION_CLUSTER_K_MIN, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(matrix)
        score = silhouette_score(matrix, labels)
        if score > best_score:
            best_k, best_labels, best_score = k, labels, score
    if best_score < _MIN_SILHOUETTE_FOR_REGION_SPLIT:
        return 1, [0] * n
    return best_k, best_labels.tolist()


def _group_payload(
    group_index: int,
    district_ids: list[str],
    district_by_id: dict[str, dict],
    district_centroids: dict[str, list[float]],
    posts: list[dict],
    district_post_indices: dict[str, list[int]],
) -> dict:
    districts_payload = []
    sample_texts: list[str] = []
    for district_id in sorted(district_ids):
        cand = district_by_id.get(district_id, {})
        districts_payload.append(
            {
                "district_id": district_id,
                "district_name": cand.get("districtName", district_id),
                "state_name": cand.get("stateName", ""),
                "state_code": cand.get("stateCode", ""),
                "centroid": district_centroids.get(district_id),
            }
        )
        for idx in district_post_indices.get(district_id, [])[:_MAX_SAMPLE_TEXTS_PER_DISTRICT]:
            if len(sample_texts) >= _MAX_SAMPLE_TEXTS_PER_GROUP:
                continue
            sample_texts.append(posts[idx]["text"][:_MAX_SAMPLE_TEXT_CHARS])
    return {"group_index": group_index, "districts": districts_payload, "sample_texts": sample_texts}


def _fallback_proposal(groups_payload: list[dict]) -> list[dict]:
    """Last-resort naming with zero LLM involvement -- used both when
    propose_regions itself returns something unusable, and as the seed for
    _assemble_regions when a specific group's proposal can't be matched back."""
    proposals = []
    for group in groups_payload:
        state_names: list[str] = []
        seen: set[str] = set()
        for d in group["districts"]:
            name = d.get("state_name")
            if name and name not in seen:
                seen.add(name)
                state_names.append(name)
        label = ", ".join(state_names[:3]) or "Unresolved geography"
        proposals.append(
            {
                "group_index": group["group_index"],
                "name": f"Region {group['group_index'] + 1} ({label})",
                "justification": (
                    f"Auto-generated from {len(group['districts'])} district(s) grouped by "
                    "embedding similarity (LLM naming was unavailable or malformed)."
                ),
            }
        )
    return proposals


def _validate_proposal(proposals: object, groups_payload: list[dict]) -> list[dict] | None:
    """Defense-in-depth re-validation of what the LLMClient implementation
    already claims to have validated -- a Protocol implementation is a
    contract, not a guarantee. Returns None (triggering the fallback) on any
    shape violation."""
    if not isinstance(proposals, list):
        return None
    by_index: dict[int, dict] = {}
    for p in proposals:
        if not isinstance(p, dict):
            return None
        idx = p.get("group_index")
        name = p.get("name")
        if not isinstance(idx, int) or not isinstance(name, str) or not name.strip():
            return None
        by_index[idx] = p
    expected = {g["group_index"] for g in groups_payload}
    if set(by_index.keys()) != expected:
        return None
    return [by_index[g["group_index"]] for g in groups_payload]


def _assemble_regions(proposals: list[dict], groups_payload: list[dict]) -> list[dict]:
    proposal_by_index = {p["group_index"]: p for p in proposals}
    regions = []
    for group in groups_payload:
        proposal = proposal_by_index.get(group["group_index"]) or _fallback_proposal([group])[0]
        regions.append(
            {
                "region_id": f"r{group['group_index']}",
                "name": proposal["name"],
                "justification": str(proposal.get("justification") or ""),
                "districts": group["districts"],
            }
        )
    return regions


def _critique_payload(regions_full: list[dict]) -> list[dict]:
    return [
        {
            "region_id": r["region_id"],
            "name": r["name"],
            "justification": r["justification"],
            "districts": [
                {
                    "district_id": d["district_id"],
                    "district_name": d["district_name"],
                    "state_name": d["state_name"],
                }
                for d in r["districts"]
            ],
        }
        for r in regions_full
    ]


def _validate_revision(revised: object, original_regions_full: list[dict]) -> list[dict] | None:
    """Enforces revise_regions' contract in code: the exact same set of
    district ids present in `original_regions_full` must appear, each in
    exactly one output region (no drops, no duplicates, no invented
    districts), no region may end up empty, and region COUNT may only stay
    the same or shrink (rename/move preserve count, merge reduces it -- a
    revision that increases region count would mean the LLM split a group
    further, which revise_regions is explicitly never allowed to do)."""
    if not isinstance(revised, list) or not revised:
        return None

    district_by_id = {d["district_id"]: d for r in original_regions_full for d in r["districts"]}
    original_ids = set(district_by_id.keys())

    seen: set[str] = set()
    rebuilt: list[dict] = []
    for entry in revised:
        if not isinstance(entry, dict):
            return None
        district_ids = entry.get("district_ids")
        name = entry.get("name")
        if not isinstance(district_ids, list) or not district_ids:
            return None
        if not isinstance(name, str) or not name.strip():
            return None
        districts = []
        for did in district_ids:
            if not isinstance(did, str) or did in seen or did not in district_by_id:
                return None
            seen.add(did)
            districts.append(district_by_id[did])
        rebuilt.append(
            {
                "region_id": str(entry.get("region_id") or f"r{len(rebuilt)}"),
                "name": name.strip(),
                "justification": str(entry.get("justification") or "").strip(),
                "districts": districts,
            }
        )

    if seen != original_ids or len(rebuilt) > len(original_regions_full):
        return None
    return rebuilt


async def infer_regions(
    state: PipelineState,
    emit: EmitFn,
    llm: LLMClient,
    gazetteer: dict,
    district_centroids: dict[str, list[float]],
) -> PipelineState:
    """Groups every RESOLVED district (post["district_id"] is not None -- set
    by geo_resolve.py's resolve_posts_geography, which must run first) into
    inferred regions, writing `state["regions"]`/`state["posts_by_region"]`
    and each covered post's `region_id` in place (mirrors how
    resolve_posts_geography itself writes state_code/district_id onto posts).
    Posts with no resolved district are bucketed under the UNKNOWN_REGION
    sentinel (mirroring geo_resolve's own UNKNOWN_STATE) with a synthetic
    RegionState, rather than silently dropped from clustering -- so a
    downstream per-region clustering stage never needs a special case for
    "this region_id has no RegionState entry"."""
    posts = state["posts"]
    total = len(posts)

    district_post_indices: dict[str, list[int]] = {}
    unresolved_indices: list[int] = []
    for idx, post in enumerate(posts):
        district_id = post.get("district_id")
        if district_id:
            district_post_indices.setdefault(district_id, []).append(idx)
        else:
            unresolved_indices.append(idx)

    if not district_post_indices:
        state["regions"] = {}
        state["posts_by_region"] = {}
        _bucket_unknown_region(posts, unresolved_indices, state["regions"], state["posts_by_region"])
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker="No resolved districts to group into regions.",
                phase="clustering",
                counts=CollectionCounts(
                    posts_collected=state["posts_collected"],
                    districts_resolved=state["districts_resolved"],
                    clusters_found=state["clusters_found"],
                    deflections_found=state["deflections_found"],
                ),
                progress=_PROGRESS,
            )
        )
        return state

    texts = [p["text"] for p in posts]
    embeddings = await llm.embed(texts) if total else []
    state["post_embeddings"] = embeddings
    matrix_all = np.array(embeddings, dtype=float)

    district_ids_sorted = sorted(district_post_indices.keys())
    district_matrix = np.array(
        [matrix_all[district_post_indices[d]].mean(axis=0) for d in district_ids_sorted],
        dtype=float,
    )

    k, labels = await asyncio.to_thread(_choose_region_k_and_labels, district_matrix)

    numeric_groups: dict[int, list[str]] = {}
    for district_id, label in zip(district_ids_sorted, labels):
        numeric_groups.setdefault(label, []).append(district_id)
    ordered_group_district_ids = [numeric_groups[lbl] for lbl in sorted(numeric_groups.keys())]

    district_by_id, _ = _build_indices(gazetteer)
    groups_payload = [
        _group_payload(i, district_ids, district_by_id, district_centroids, posts, district_post_indices)
        for i, district_ids in enumerate(ordered_group_district_ids)
    ]

    try:
        raw_proposals = await llm.propose_regions(groups_payload)
    except Exception as exc:  # noqa: BLE001
        print(f"[infer_regions] propose_regions raised, falling back: {exc}", flush=True)
        raw_proposals = None
    proposals = _validate_proposal(raw_proposals, groups_payload)
    used_fallback_naming = proposals is None
    if proposals is None:
        print(
            f"[infer_regions] propose_regions returned an unusable shape for {len(groups_payload)} "
            "group(s), falling back to auto-generated names",
            flush=True,
        )
        proposals = _fallback_proposal(groups_payload)

    regions_full = _assemble_regions(proposals, groups_payload)
    was_revised = False

    for revision_round in range(REGION_REVISION_ROUND_CAP + 1):
        try:
            critique = await llm.critique_regions(_critique_payload(regions_full))
        except Exception as exc:  # noqa: BLE001
            print(f"[infer_regions] critique_regions raised, treating as approved: {exc}", flush=True)
            critique = {"approved": True, "notes": "", "flagged_district_ids": []}
        if not isinstance(critique, dict) or critique.get("approved", True):
            break
        if revision_round == REGION_REVISION_ROUND_CAP:
            # Revision budget exhausted -- force-accept the current partition
            # rather than trust the LLM to eventually stop objecting.
            break
        try:
            raw_revised = await llm.revise_regions(_critique_payload(regions_full), critique)
        except Exception as exc:  # noqa: BLE001
            print(f"[infer_regions] revise_regions raised, keeping current partition: {exc}", flush=True)
            break
        validated = _validate_revision(raw_revised, regions_full)
        if validated is None:
            print(
                "[infer_regions] revise_regions output failed district-set validation, "
                "keeping pre-revision partition",
                flush=True,
            )
            break
        regions_full = validated
        was_revised = True

    confidence = "low" if used_fallback_naming else ("medium" if was_revised else "high")

    regions: dict[str, RegionState] = {}
    posts_by_region: dict[str, list[str]] = {}
    for r in regions_full:
        district_ids_in_region = [d["district_id"] for d in r["districts"]]
        state_codes = sorted({d["state_code"] for d in r["districts"] if d.get("state_code")})
        region_id = r["region_id"]
        regions[region_id] = RegionState(
            id=region_id,
            name=r["name"],
            justification=r["justification"],
            district_ids=district_ids_in_region,
            state_codes=state_codes,
            confidence=confidence,
            worldview_text="",
        )
        post_ids = []
        for district_id in district_ids_in_region:
            for idx in district_post_indices.get(district_id, []):
                posts[idx]["region_id"] = region_id
                post_ids.append(posts[idx]["id"])
        posts_by_region[region_id] = post_ids

    _bucket_unknown_region(posts, unresolved_indices, regions, posts_by_region)

    state["regions"] = regions
    state["posts_by_region"] = posts_by_region

    # One event per region (including the UNK-REGION sentinel bucket, if
    # present -- it already has a synthetic name/justification from
    # _bucket_unknown_region) so the frontend learns each regionId's actual
    # name/membership before any cluster_defined/district_resolved event
    # references it -- those only carry the bare id.
    for region_id, region in regions.items():
        await emit(
            RegionDefinedEvent(
                query_run_id=state["query_run_id"],
                region_id=region_id,
                name=region["name"],
                justification=region["justification"],
                district_ids=region["district_ids"],
                state_codes=region["state_codes"],
                confidence=region["confidence"],
            )
        )

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Inferred {len(regions)} region{'s' if len(regions) != 1 else ''} from "
                f"{len(district_post_indices)} resolved districts."
            ),
            phase="clustering",
            counts=CollectionCounts(
                posts_collected=state["posts_collected"],
                districts_resolved=state["districts_resolved"],
                clusters_found=state["clusters_found"],
                deflections_found=state["deflections_found"],
            ),
            progress=_PROGRESS,
        )
    )

    return state
