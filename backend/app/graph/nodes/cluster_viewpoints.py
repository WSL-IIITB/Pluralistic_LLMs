"""
Groups each Karnataka region's posts into distinct viewpoints, region by region
(state["posts_by_region"], from resolve_regions.py), so a low-volume region's
genuine viewpoint can't be absorbed into a high-volume region's dominant one.

One `llm.embed()` call for the whole corpus, then per region: a silhouette-swept
KMeans (_choose_k_and_labels), an LLM label/summary per cluster, and a couple of
paraphrased representative posts. Emits one ClusterDefinedEvent per cluster.
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


# Bounds how many regions cluster concurrently.
_MAX_CONCURRENT_REGION_CLUSTERING = 6

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
# geographically-diverse runs to a single cluster. Lowered to let real-but-modest separation through --
# still strictly positive (a negative/near-zero score is genuine noise, not
# signal worth splitting on), just no longer demanding near-textbook
# cluster separation from inherently short, noisy text.
_MIN_SILHOUETTE_FOR_SPLIT = 0.03


def _choose_k_and_labels(matrix: np.ndarray) -> tuple[int, list[int]]:
    """Dynamic cluster count for one region's posts: sweeps k over
    [EXTRAHIGH_CLUSTER_K_MIN, k_max] and picks the k maximizing silhouette
    score, so a region's cluster count reflects genuine separability in its
    own embedding space -- a homogeneous region lands on a small k, a
    genuinely diverse one can reach the wider ceiling. `k_max` is also
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


async def cluster_viewpoints_per_region(state: PipelineState, emit: EmitFn, llm: LLMClient) -> PipelineState:
    """Cluster each region's posts independently (see module docstring)."""
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

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REGION_CLUSTERING)
    regions_done = 0
    total_regions = len(state["posts_by_region"])

    async def _cluster_one_region(region_id: str, post_ids: list[str]) -> None:
        idxs = [id_to_index[pid] for pid in post_ids if pid in id_to_index]
        if not idxs:
            return
        sub_matrix = matrix_all[idxs]

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
                "state_code": "29",
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
                    state_code="29",
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
