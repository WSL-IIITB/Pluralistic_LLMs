"""
Second pipeline stage: groups sourced posts into distinct viewpoints.

Runs BEFORE district resolution (source -> cluster -> resolve_district ->
deflection -> synthesize) because the frontend's `district_resolved` event
requires a clusterId on every post, so every RawPost must already carry one
by the time the resolver aggregates volume per (district, cluster).

Flow: embed every post's text (`llm.embed`), split the embedding matrix into
`k` groups with scikit-learn's `KMeans` (a single group when there are too
few posts to cluster meaningfully), then ask the LLM to label/summarize each
group and paraphrase a couple of its posts for display. Each post's
`cluster_id` is set in place, `state["clusters"]`/`state["cluster_order"]`
are populated, and one `ClusterDefinedEvent` per cluster plus a single
trailing `StatusEvent` are emitted.
"""

from __future__ import annotations

import asyncio

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ..state import ClusterState, EmitFn, PipelineState
from ...connectors.base import LLMClient
from ...reasoning_modes import (
    EXTRAHIGH_CLUSTER_K_MAX,
    EXTRAHIGH_CLUSTER_K_MIN,
    EXTRAHIGH_MIN_POSTS_PER_CLUSTER,
)
from ...schema import ClusterDefinedEvent, CollectionCounts, SamplePost, StatusEvent

# Mirrors the frontend's --cluster-1..6 categorical tokens. Cycled (modulo)
# if a run ever produces more than 6 groups, which shouldn't happen given the
# k heuristic below but is handled defensively anyway.
_PALETTE: list[list[int]] = [
    [249, 183, 63],
    [250, 137, 39],
    [233, 72, 61],
    [225, 90, 123],
    [238, 208, 89],
    [243, 126, 97],
]

_MAX_LABEL_SAMPLES = 3
_MAX_REPRESENTATIVE_POSTS = 2


async def cluster_viewpoints(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    posts = state["posts"]
    texts = [p["text"] for p in posts]
    n = len(texts)

    if n == 0:
        state["phase"] = "clustering"
        counts = CollectionCounts(
            posts_collected=state["posts_collected"],
            districts_resolved=state["districts_resolved"],
            clusters_found=state["clusters_found"],
            deflections_found=state["deflections_found"],
        )
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker="No posts collected to cluster.",
                phase="clustering",
                counts=counts,
                progress=0.55,
            )
        )
        return state

    embeddings = await llm.embed(texts)

    if n < 4:
        # Too few posts for a meaningful split — everything is one viewpoint.
        labels = [0] * n
    else:
        k = min(6, max(2, n // 6))
        k = max(1, min(k, n))  # defensive: KMeans requires n_clusters <= n_samples
        matrix = np.array(embeddings, dtype=float)
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(matrix).tolist()

    # Group post indices by their raw KMeans label, then assign each group a
    # stable, zero-based cluster index (0..len(groups)-1) — this is what
    # feeds both the "cN" cluster_id and the palette lookup.
    groups: dict[int, list[int]] = {}
    for idx, lbl in enumerate(labels):
        groups.setdefault(lbl, []).append(idx)

    # Each cluster's LLM work (label + a couple of paraphrases) is independent
    # of every other cluster's, so it runs CONCURRENTLY -- with real API
    # latency this was the dominant cost of the whole stage otherwise (one
    # cluster fully sequential after another). Events still emit as each
    # cluster's work finishes (via as_completed), so the progressive reveal
    # the frontend expects is preserved; only the underlying compute is
    # parallel, not the order posts/state are touched in.
    async def _process_cluster(cluster_index: int, idxs: list[int]) -> tuple[
        str, list[int], str, str, list[int], list[SamplePost]
    ]:
        cluster_id = f"c{cluster_index}"
        color = _PALETTE[cluster_index % len(_PALETTE)]
        sample_texts = [texts[idx] for idx in idxs[:_MAX_LABEL_SAMPLES]]
        label, summary = await llm.label_cluster(sample_texts)

        representative_sample_posts: list[SamplePost] = []
        for idx in idxs[:_MAX_REPRESENTATIVE_POSTS]:
            post = posts[idx]
            paraphrase = await llm.paraphrase(post["text"])
            representative_sample_posts.append(
                SamplePost(
                    id=post["id"],
                    platform=post["platform"],  # type: ignore[arg-type]
                    paraphrase=paraphrase,
                    cluster_id=cluster_id,
                    url=post.get("permalink"),
                )
            )
        return cluster_id, idxs, label, summary, color, representative_sample_posts

    tasks = [
        asyncio.ensure_future(_process_cluster(cluster_index, groups[raw_label]))
        for cluster_index, raw_label in enumerate(sorted(groups.keys()))
    ]

    for finished in asyncio.as_completed(tasks):
        cluster_id, idxs, label, summary, color, representative_sample_posts = await finished
        representative_posts_dicts = [
            sp.model_dump(by_alias=True, exclude_none=True) for sp in representative_sample_posts
        ]

        for idx in idxs:
            posts[idx]["cluster_id"] = cluster_id

        cluster_state: ClusterState = {
            "id": cluster_id,
            "label": label,
            "color": color,
            "summary": summary,
            "representative_posts": representative_posts_dicts,
            "post_ids": [posts[idx]["id"] for idx in idxs],
            "state_code": None,
            "region_id": None,
        }
        state["clusters"][cluster_id] = cluster_state
        state["cluster_order"].append(cluster_id)

        await emit(
            ClusterDefinedEvent(
                query_run_id=state["query_run_id"],
                cluster_id=cluster_id,
                label=label,
                color=color,
                summary=summary,
                representative_posts=representative_sample_posts,
            )
        )

    state["clusters_found"] = len(state["clusters"])
    state["phase"] = "clustering"

    counts = CollectionCounts(
        posts_collected=state["posts_collected"],
        districts_resolved=state["districts_resolved"],
        clusters_found=state["clusters_found"],
        deflections_found=state["deflections_found"],
    )
    n_clusters = state["clusters_found"]
    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=f"Grouped {n} posts into {n_clusters} distinct viewpoint{'s' if n_clusters != 1 else ''}.",
            phase="clustering",
            counts=counts,
            progress=0.55,
        )
    )

    return state


# extrahigh mode only, below this point -- everything above is untouched.

# Mirrors build.py's _MAX_CONCURRENT_FETCHES naming/style: bounds how many
# states cluster concurrently, not how much CPU/LLM work each one does.
_MAX_CONCURRENT_STATE_CLUSTERING = 6

_CLUSTER_PROGRESS_START = 0.5
_CLUSTER_PROGRESS_END = 0.68

# Silhouette score is only computable for k >= 2, so a genuinely homogeneous
# state (no real split at all) can't be directly compared against "no split"
# within the same sweep -- every candidate k in the sweep will still get SOME
# score, even for pure noise, and small-n low-signal data can occasionally
# score deceptively well by chance. This floor is the fallback: if even the
# BEST k the sweep found scores below it, treat that as "no real structure
# found" and collapse to a single cluster rather than accepting a weak,
# likely-spurious split.
#
# 0.15 was the original choice, framed as "permissive" -- in practice it was
# too conservative for short social-media text embeddings (sentence-
# transformers on brief, template-y posts rarely separates as cleanly as
# long-form documents do), and was observed collapsing genuinely
# geographically-diverse runs (15 real districts across 11 different states)
# to a single cluster. Lowered to let real-but-modest separation through --
# still strictly positive (a negative/near-zero score is genuine noise, not
# signal worth splitting on), just no longer demanding near-textbook
# cluster separation from inherently short, noisy text.
_MIN_SILHOUETTE_FOR_SPLIT = 0.03


def _choose_k_and_labels(matrix: np.ndarray) -> tuple[int, list[int]]:
    """Dynamic cluster count for one state's posts, replacing the fixed
    `k = min(6, max(2, n // 6))` heuristic above (which stays exactly as-is
    for basic/medium/high). Sweeps k over [EXTRAHIGH_CLUSTER_K_MIN, k_max]
    and picks the k maximizing silhouette score, so a state's cluster count
    reflects genuine separability in its own embedding space rather than a
    size-only formula -- a homogeneous state naturally lands on a small k,
    a genuinely diverse one can reach the wider ceiling. `k_max` is also
    capped by EXTRAHIGH_MIN_POSTS_PER_CLUSTER so the sweep never proposes a k
    that would average fewer than ~3 posts per cluster (a 1-post "cluster"
    has no real viewpoint to summarize, only an echo of that one post).
    Returns (k, labels), reusing the winning sweep's own fit rather than
    re-fitting once a k is chosen."""
    n = matrix.shape[0]
    if n < 4:
        return 1, [0] * n
    k_max = min(EXTRAHIGH_CLUSTER_K_MAX, n // EXTRAHIGH_MIN_POSTS_PER_CLUSTER, n - 1)
    if k_max < EXTRAHIGH_CLUSTER_K_MIN:
        return 1, [0] * n
    best_k, best_labels, best_score = EXTRAHIGH_CLUSTER_K_MIN, None, -1.0
    for k in range(EXTRAHIGH_CLUSTER_K_MIN, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(matrix)
        score = silhouette_score(matrix, labels)
        if score > best_score:
            best_k, best_labels, best_score = k, labels, score
    if best_score < _MIN_SILHOUETTE_FOR_SPLIT:
        return 1, [0] * n
    return best_k, best_labels.tolist()


async def cluster_viewpoints_per_state(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode counterpart to `cluster_viewpoints`: instead of one
    global embed + KMeans pass over every post, clusters EACH STATE's posts
    independently (state["posts_by_state"], populated by geo_resolve.py's
    resolve_posts_geography, which must run first). A low-volume state's
    genuine viewpoint can no longer get absorbed into a high-volume state's
    dominant cluster the way it can under global clustering.

    Still issues exactly ONE `llm.embed()` call for the whole corpus (sliced
    per state afterward) -- embedding is naturally batchable and re-calling it
    per state would multiply an already-cheap operation for no benefit.
    States are clustered CONCURRENTLY, bounded by
    `_MAX_CONCURRENT_STATE_CLUSTERING`, streaming `ClusterDefinedEvent`s as
    each state's clusters resolve (one level up from the per-cluster
    `as_completed` pattern `cluster_viewpoints` already uses above).

    Deliberately does not share code with `cluster_viewpoints` above (the
    per-cluster labeling/paraphrase body is duplicated here) so that function
    stays completely untouched -- extracting a shared helper is a safe,
    optional follow-up, not required for this to be correct."""
    posts = state["posts"]
    n = len(posts)

    if n == 0:
        state["phase"] = "clustering"
        counts = CollectionCounts(
            posts_collected=state["posts_collected"],
            districts_resolved=state["districts_resolved"],
            clusters_found=state["clusters_found"],
            deflections_found=state["deflections_found"],
        )
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker="No posts collected to cluster.",
                phase="clustering",
                counts=counts,
                progress=_CLUSTER_PROGRESS_END,
            )
        )
        return state

    texts = [p["text"] for p in posts]
    embeddings = await llm.embed(texts)
    matrix_all = np.array(embeddings, dtype=float)
    id_to_index = {p["id"]: i for i, p in enumerate(posts)}

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_STATE_CLUSTERING)
    states_done = 0
    total_states = len(state["posts_by_state"])

    async def _cluster_one_state(state_code: str, post_ids: list[str]) -> None:
        idxs = [id_to_index[pid] for pid in post_ids if pid in id_to_index]
        if not idxs:
            return
        sub_matrix = matrix_all[idxs]

        async with semaphore:
            # KMeans + a silhouette sweep is synchronous CPU work; run it off
            # the event loop since this now runs concurrently across states,
            # unlike the single global call above.
            k, local_labels = await asyncio.to_thread(_choose_k_and_labels, sub_matrix)

        groups: dict[int, list[int]] = {}
        for local_idx, lbl in zip(idxs, local_labels):
            groups.setdefault(lbl, []).append(local_idx)

        async def _process_cluster(cluster_index: int, group_idxs: list[int]) -> tuple[
            str, list[int], str, str, list[int], list[SamplePost]
        ]:
            cluster_id = f"{state_code}:c{cluster_index}"
            color = _PALETTE[cluster_index % len(_PALETTE)]
            sample_texts = [texts[idx] for idx in group_idxs[:_MAX_LABEL_SAMPLES]]
            label, summary = await llm.label_cluster(sample_texts)

            representative_sample_posts: list[SamplePost] = []
            for idx in group_idxs[:_MAX_REPRESENTATIVE_POSTS]:
                post = posts[idx]
                paraphrase = await llm.paraphrase(post["text"])
                representative_sample_posts.append(
                    SamplePost(
                        id=post["id"],
                        platform=post["platform"],  # type: ignore[arg-type]
                        paraphrase=paraphrase,
                        cluster_id=cluster_id,
                        url=post.get("permalink"),
                    )
                )
            return cluster_id, group_idxs, label, summary, color, representative_sample_posts

        cluster_tasks = [
            asyncio.ensure_future(_process_cluster(cluster_index, groups[raw_label]))
            for cluster_index, raw_label in enumerate(sorted(groups.keys()))
        ]

        for finished in asyncio.as_completed(cluster_tasks):
            cluster_id, group_idxs, label, summary, color, representative_sample_posts = await finished
            representative_posts_dicts = [
                sp.model_dump(by_alias=True, exclude_none=True) for sp in representative_sample_posts
            ]

            for idx in group_idxs:
                posts[idx]["cluster_id"] = cluster_id

            cluster_state: ClusterState = {
                "id": cluster_id,
                "label": label,
                "color": color,
                "summary": summary,
                "representative_posts": representative_posts_dicts,
                "post_ids": [posts[idx]["id"] for idx in group_idxs],
                "state_code": state_code,
                "region_id": None,
            }
            state["clusters"][cluster_id] = cluster_state
            state["cluster_order"].append(cluster_id)

            await emit(
                ClusterDefinedEvent(
                    query_run_id=state["query_run_id"],
                    cluster_id=cluster_id,
                    label=label,
                    color=color,
                    summary=summary,
                    representative_posts=representative_sample_posts,
                    state_code=state_code,
                )
            )

        nonlocal states_done
        states_done += 1
        progress = (
            _CLUSTER_PROGRESS_START
            + (_CLUSTER_PROGRESS_END - _CLUSTER_PROGRESS_START) * (states_done / total_states)
        )
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=f"Clustered {states_done}/{total_states} states ({len(groups)} viewpoints in {state_code})…",
                phase="clustering",
                counts=CollectionCounts(
                    posts_collected=state["posts_collected"],
                    districts_resolved=state["districts_resolved"],
                    clusters_found=len(state["clusters"]),
                    deflections_found=state["deflections_found"],
                ),
                progress=progress,
            )
        )

    state_tasks = [
        asyncio.ensure_future(_cluster_one_state(state_code, post_ids))
        for state_code, post_ids in state["posts_by_state"].items()
    ]
    for finished in asyncio.as_completed(state_tasks):
        await finished

    state["clusters_found"] = len(state["clusters"])
    state["phase"] = "clustering"

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Grouped {n} posts into {state['clusters_found']} distinct viewpoints "
                f"across {total_states} states."
            ),
            phase="clustering",
            counts=CollectionCounts(
                posts_collected=state["posts_collected"],
                districts_resolved=state["districts_resolved"],
                clusters_found=state["clusters_found"],
                deflections_found=state["deflections_found"],
            ),
            progress=_CLUSTER_PROGRESS_END,
        )
    )

    return state


def _representative_state_code(
    posts: list, id_to_index: dict[str, int], post_ids: list[str]
) -> str | None:
    """The region's highest-post-volume district's state -- see
    ClusterState's state_code docstring for why region-mode clusters need a
    representative single-state value instead of their own true (possibly
    multi-state) membership."""
    volume_by_district: dict[str, int] = {}
    state_of_district: dict[str, str] = {}
    for pid in post_ids:
        idx = id_to_index.get(pid)
        if idx is None:
            continue
        post = posts[idx]
        district_id = post.get("district_id")
        if not district_id:
            continue
        volume_by_district[district_id] = volume_by_district.get(district_id, 0) + 1
        if district_id not in state_of_district and post.get("state_code"):
            state_of_district[district_id] = post["state_code"]
    if not volume_by_district:
        return None
    top_district_id = max(volume_by_district.items(), key=lambda kv: kv[1])[0]
    return state_of_district.get(top_district_id)


async def cluster_viewpoints_per_region(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """extrahigh-mode counterpart to `cluster_viewpoints_per_state`, scoped to
    AGENT-INFERRED REGIONS (state["posts_by_region"], populated by
    graph/nodes/infer_regions.py, which must run first) instead of fixed
    administrative states -- a region can span several districts and cross
    multiple state boundaries. Straight copy-and-rename of
    `cluster_viewpoints_per_state`'s body (this module's own established
    pattern: independently-evolving per-scope variants stay decoupled rather
    than sharing code), with one efficiency difference: reuses
    `state["post_embeddings"]` (already computed by infer_regions.py's own
    `llm.embed()` call over the same corpus) instead of embedding a second
    time.

    Every ClusterState/ClusterDefinedEvent produced here carries BOTH the new
    authoritative `region_id` AND a transitional, representative `state_code`
    (the region's highest-post-volume district's state) -- see ClusterState's
    state_code docstring for why that backward-compat shim exists."""
    posts = state["posts"]
    n = len(posts)

    if n == 0:
        state["phase"] = "clustering"
        counts = CollectionCounts(
            posts_collected=state["posts_collected"],
            districts_resolved=state["districts_resolved"],
            clusters_found=state["clusters_found"],
            deflections_found=state["deflections_found"],
        )
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker="No posts collected to cluster.",
                phase="clustering",
                counts=counts,
                progress=_CLUSTER_PROGRESS_END,
            )
        )
        return state

    texts = [p["text"] for p in posts]
    embeddings = state.get("post_embeddings")
    if not embeddings:
        # Defensive fallback -- infer_regions.py should always have set this
        # by the time this node runs, but never block clustering on that
        # invariant holding.
        embeddings = await llm.embed(texts)
    matrix_all = np.array(embeddings, dtype=float)
    id_to_index = {p["id"]: i for i, p in enumerate(posts)}

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_STATE_CLUSTERING)
    regions_done = 0
    total_regions = len(state["posts_by_region"])

    async def _cluster_one_region(region_id: str, post_ids: list[str]) -> None:
        idxs = [id_to_index[pid] for pid in post_ids if pid in id_to_index]
        if not idxs:
            return
        sub_matrix = matrix_all[idxs]
        representative_state_code = _representative_state_code(posts, id_to_index, post_ids)

        async with semaphore:
            # KMeans + a silhouette sweep is synchronous CPU work; run it off
            # the event loop since this now runs concurrently across regions,
            # unlike the single global call above.
            k, local_labels = await asyncio.to_thread(_choose_k_and_labels, sub_matrix)

        groups: dict[int, list[int]] = {}
        for local_idx, lbl in zip(idxs, local_labels):
            groups.setdefault(lbl, []).append(local_idx)

        async def _process_cluster(cluster_index: int, group_idxs: list[int]) -> tuple[
            str, list[int], str, str, list[int], list[SamplePost]
        ]:
            cluster_id = f"{region_id}:c{cluster_index}"
            color = _PALETTE[cluster_index % len(_PALETTE)]
            sample_texts = [texts[idx] for idx in group_idxs[:_MAX_LABEL_SAMPLES]]
            label, summary = await llm.label_cluster(sample_texts)

            representative_sample_posts: list[SamplePost] = []
            for idx in group_idxs[:_MAX_REPRESENTATIVE_POSTS]:
                post = posts[idx]
                paraphrase = await llm.paraphrase(post["text"])
                representative_sample_posts.append(
                    SamplePost(
                        id=post["id"],
                        platform=post["platform"],  # type: ignore[arg-type]
                        paraphrase=paraphrase,
                        cluster_id=cluster_id,
                        url=post.get("permalink"),
                    )
                )
            return cluster_id, group_idxs, label, summary, color, representative_sample_posts

        cluster_tasks = [
            asyncio.ensure_future(_process_cluster(cluster_index, groups[raw_label]))
            for cluster_index, raw_label in enumerate(sorted(groups.keys()))
        ]

        for finished in asyncio.as_completed(cluster_tasks):
            cluster_id, group_idxs, label, summary, color, representative_sample_posts = await finished
            representative_posts_dicts = [
                sp.model_dump(by_alias=True, exclude_none=True) for sp in representative_sample_posts
            ]

            for idx in group_idxs:
                posts[idx]["cluster_id"] = cluster_id

            cluster_state: ClusterState = {
                "id": cluster_id,
                "label": label,
                "color": color,
                "summary": summary,
                "representative_posts": representative_posts_dicts,
                "post_ids": [posts[idx]["id"] for idx in group_idxs],
                "state_code": representative_state_code,
                "region_id": region_id,
            }
            state["clusters"][cluster_id] = cluster_state
            state["cluster_order"].append(cluster_id)

            await emit(
                ClusterDefinedEvent(
                    query_run_id=state["query_run_id"],
                    cluster_id=cluster_id,
                    label=label,
                    color=color,
                    summary=summary,
                    representative_posts=representative_sample_posts,
                    state_code=representative_state_code,
                    region_id=region_id,
                )
            )

        nonlocal regions_done
        regions_done += 1
        progress = (
            _CLUSTER_PROGRESS_START
            + (_CLUSTER_PROGRESS_END - _CLUSTER_PROGRESS_START) * (regions_done / total_regions)
        )
        region_name = state["regions"].get(region_id, {}).get("name", region_id)
        await emit(
            StatusEvent(
                query_run_id=state["query_run_id"],
                ticker=(
                    f"Clustered {regions_done}/{total_regions} regions "
                    f"({len(groups)} viewpoints in {region_name})…"
                ),
                phase="clustering",
                counts=CollectionCounts(
                    posts_collected=state["posts_collected"],
                    districts_resolved=state["districts_resolved"],
                    clusters_found=len(state["clusters"]),
                    deflections_found=state["deflections_found"],
                ),
                progress=progress,
            )
        )

    region_tasks = [
        asyncio.ensure_future(_cluster_one_region(region_id, post_ids))
        for region_id, post_ids in state["posts_by_region"].items()
    ]
    for finished in asyncio.as_completed(region_tasks):
        await finished

    state["clusters_found"] = len(state["clusters"])
    state["phase"] = "clustering"

    await emit(
        StatusEvent(
            query_run_id=state["query_run_id"],
            ticker=(
                f"Grouped {n} posts into {state['clusters_found']} distinct viewpoints "
                f"across {total_regions} regions."
            ),
            phase="clustering",
            counts=CollectionCounts(
                posts_collected=state["posts_collected"],
                districts_resolved=state["districts_resolved"],
                clusters_found=state["clusters_found"],
                deflections_found=state["deflections_found"],
            ),
            progress=_CLUSTER_PROGRESS_END,
        )
    )

    return state
